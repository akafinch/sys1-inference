"""The GPU host's bootstrap, checked without a GPU or an Akamai account.

Terraform itself renders the cloud-init template, with the variables build/infra/main.tf passes
and the values its example and auto variable files give; cloud-init validates the result; and the
files the host runs are checked for what they pin: OpenJev's image tag, both checkpoints'
revisions, and the one port the host publishes.
"""

import base64
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
INFRA = ROOT / "build" / "infra"
DEPLOY = ROOT / "src" / "deploy"
TEMPLATE = DEPLOY / "cloud-init.yaml.tftpl"

NINE = {
    "repo_url",
    "repo_ref",
    "app_port",
    "openjev_version",
    "diffusiongemma_model",
    "diffusiongemma_revision",
    "laya_model",
    "laya_revision",
    "nvidia_driver_branch",
}
REVISION = re.compile(r"[0-9a-f]{40}")
# The image tag comes only from the settings file, and compose stops if it is missing.
PINNED_IMAGE = re.compile(r"razorback16/openjev(-laya)?:\$\{OPENJEV_VERSION:\?[^}]+\}")
# Akamai's limit on base64-encoded user data: https://techdocs.akamai.com/linode-api/reference/post-linode-instance
USER_DATA_LIMIT = 65_535


def templatefile_vars() -> dict[str, str]:
    """The variables main.tf passes to the template, as name -> Terraform expression."""
    main = (INFRA / "main.tf").read_text()
    call = re.search(r'templatefile\("\$\{path\.module\}/\.\./\.\./src/deploy/cloud-init\.yaml\.tftpl",\s*\{(.*?)\}\)', main, re.S)
    assert call, "main.tf no longer renders src/deploy/cloud-init.yaml.tftpl"
    return dict(re.findall(r"^\s*(\w+)\s*=\s*(.+?)\s*$", call.group(1), re.M))


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    """The user data as `terraform plan` would send it, rendered by Terraform's own templatefile().

    terraform console runs in a scratch directory holding only the module's variables and its
    two variable files (the example copied to terraform.tfvars, which Terraform loads by itself),
    so it needs no provider, no token and no network.
    """
    if shutil.which("terraform") is None:
        pytest.skip("terraform is not installed")
    work = tmp_path_factory.mktemp("render")
    shutil.copy(INFRA / "variables.tf", work)
    shutil.copy(INFRA / "adp.auto.tfvars.json", work)
    shutil.copy(INFRA / "terraform.tfvars.example", work / "terraform.tfvars")
    passed = "{" + ", ".join(f"{name} = {expression}" for name, expression in templatefile_vars().items()) + "}"
    expression = f'jsonencode({{user_data = base64encode(templatefile("{TEMPLATE}", {passed})), vars = {passed}}})'
    environment = {name: value for name, value in os.environ.items() if not name.startswith("TF_")}
    console = subprocess.run(["terraform", "console"], input=expression, cwd=work, env=environment, capture_output=True, text=True)
    assert console.returncode == 0, console.stderr
    result = json.loads(json.loads(console.stdout))  # console prints the JSON as a quoted string
    text = base64.b64decode(result["user_data"]).decode()
    path = work / "user-data.yaml"
    path.write_text(text)
    return SimpleNamespace(user_data=result["user_data"], text=text, path=path, vars=result["vars"], config=yaml.safe_load(text))


def settings(rendered) -> dict[str, str]:
    """/etc/sys1.env as the user data writes it."""
    [file] = [f for f in rendered.config["write_files"] if f["path"] == "/etc/sys1.env"]
    lines = [line for line in file["content"].splitlines() if line and not line.startswith("#")]
    return dict(line.split("=", 1) for line in lines)


def services() -> dict[str, dict]:
    return yaml.safe_load((DEPLOY / "compose.yaml").read_text())["services"]


def test_the_template_takes_exactly_the_nine_variables_main_tf_passes():
    assert set(templatefile_vars()) == NINE
    # ${name} is Terraform's; an escaped $${...} is not.
    used = set(re.findall(r"(?<!\$)\$\{\s*(\w+)\s*\}", TEMPLATE.read_text()))
    assert used == NINE


def test_the_rendered_bootstrap_is_valid_cloud_config(rendered):
    if shutil.which("cloud-init") is None:
        pytest.skip("cloud-init is not installed")
    assert rendered.text.startswith("#cloud-config\n")
    # Exit 0 when valid; run as a non-root user it also prints permission warnings on stderr.
    check = subprocess.run(["cloud-init", "schema", "-c", str(rendered.path)], capture_output=True, text=True)
    assert check.returncode == 0, check.stdout + check.stderr


def test_the_user_data_fits_akamai_s_limit(rendered):
    assert len(rendered.user_data) <= USER_DATA_LIMIT


def test_the_bootstrap_stops_at_an_error_and_reboots_only_once_it_finished(rendered):
    runcmd, power = rendered.config["runcmd"], rendered.config["power_state"]
    assert runcmd[0] == "set -eu"
    assert power["mode"] == "reboot"
    marker = re.fullmatch(r"test -f (\S+)", power["condition"]).group(1)
    # The mark is made after every step it vouches for: only the closing message follows it.
    after = runcmd[runcmd.index(f"touch {marker}") + 1 :]
    assert all(step.startswith("say ") for step in after), after


def test_images_are_pinned_never_latest(rendered):
    for name, service in services().items():
        if "image" in service:
            assert PINNED_IMAGE.fullmatch(service["image"]), name
        else:
            assert "build" in service, name  # the app, built on the host
    assert settings(rendered)["OPENJEV_VERSION"] == rendered.vars["openjev_version"]
    for text in (rendered.text, (DEPLOY / "compose.yaml").read_text(), (DEPLOY / "app.Dockerfile").read_text()):
        assert "latest" not in text
    # Every base image names its tag.
    for image in re.findall(r"^FROM\s+(\S+)", (DEPLOY / "app.Dockerfile").read_text(), re.M):
        assert ":" in image.rsplit("/", 1)[-1], image
    # The weights step runs the pinned Laya image too.
    for reference in re.findall(r"razorback16/openjev[\w-]*\S*", (DEPLOY / "bringup.sh").read_text()):
        assert reference.startswith("razorback16/openjev-laya:$OPENJEV_VERSION"), reference


def test_both_checkpoints_are_pinned_by_revision(rendered):
    env = settings(rendered)
    for model in ("diffusiongemma", "laya"):
        assert REVISION.fullmatch(env[f"{model.upper()}_REVISION"])
        assert env[f"{model.upper()}_REVISION"] == rendered.vars[f"{model}_revision"]
        assert env[f"{model.upper()}_MODEL"] == rendered.vars[f"{model}_model"]
    assert 'hf download "$repo" --revision "$revision"' in (DEPLOY / "bringup.sh").read_text()


def test_only_the_app_publishes_a_port_beyond_loopback_and_the_firewall_opens_it(rendered):
    published = {}
    for name, service in services().items():
        assert "network_mode" not in service, name  # host networking would publish every port
        for port in service.get("ports", []):
            if not str(port).startswith("127.0.0.1:"):
                published.setdefault(name, []).append(port)
    assert list(published) == ["app"]
    [port] = published["app"]
    assert re.fullmatch(r"0\.0\.0\.0:\$\{APP_PORT:\?[^}]+\}:\$\{APP_PORT:\?[^}]+\}", port)
    # The settings file sets that port from app_port, which the firewall's page rule opens.
    assert settings(rendered)["APP_PORT"] == str(rendered.vars["app_port"])
    assert re.search(r"ports\s*=\s*tostring\(var\.app_port\)", (INFRA / "main.tf").read_text())


def test_every_service_restarts_unless_stopped():
    for name, service in services().items():
        assert service.get("restart") == "unless-stopped", name


def test_every_compose_call_reads_the_settings_file():
    for script in ("bringup.sh", "update.sh"):
        calls = [line for line in (DEPLOY / script).read_text().splitlines() if "docker compose" in line and not line.lstrip().startswith("#")]
        assert calls, script
        for line in calls:
            assert "--env-file /etc/sys1.env" in line, (script, line)
    # and compose.yaml requires what the file sets, rather than defaulting it
    for variable in re.findall(r"\$\{[^}]*\}", (DEPLOY / "compose.yaml").read_text()):
        assert re.fullmatch(r"\$\{\w+:\?[^}]+\}", variable), variable


def test_the_bring_up_service_runs_the_script_this_repository_ships(rendered):
    [unit] = [f for f in rendered.config["write_files"] if f["path"] == "/etc/systemd/system/sys1-bringup.service"]
    assert "EnvironmentFile=/etc/sys1.env" in unit["content"]
    assert "ExecStart=/bin/bash /opt/sys1/src/deploy/bringup.sh" in unit["content"]
    assert (DEPLOY / "bringup.sh").is_file()
    assert any(step.startswith("git clone ") and step.endswith(" /opt/sys1") for step in rendered.config["runcmd"])
    assert "systemctl enable sys1-bringup.service" in rendered.config["runcmd"]
