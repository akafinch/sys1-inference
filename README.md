# System 1 Inference on Akamai

A live demo of open System 1 decision models, DiffusionGemma 26B-A4B and Laya, served through
[OpenJev](https://github.com/razorback16/openjev) on one Akamai GPU instance. You ask a model a
typed question about a sample text (a choice, a score or a yes/no) and get back a probability
distribution in one pass, with the time each leg of the trip took.

> **The demo's GPU plan, NVIDIA RTX PRO 6000 Blackwell (`g3-gpu-rtxpro6000-blackwell-1`, listed
> at $3.00/hour to our account on 2026-09-30), has limited availability: request access for your
> own account, and check its price there, before you deploy.**

## Where it runs

Everything runs on one GPU Linode that Terraform creates, in four containers:

- `openjev`: DiffusionGemma, served by vLLM inside OpenJev's image, behind OpenJev's API;
- `laya-gpu`: Laya's typed-decisions checkpoint on the same card;
- `laya-cpu`: the same checkpoint on the host's CPU, so the page can compare devices;
- `app`: a FastAPI backend serving the Svelte page (`src/app`, `src/web`).

The browser talks only to the app; the app talks to OpenJev over the host's own Docker network.
No model runs anywhere else.

## How the code gets onto the host

Terraform ([`build/infra/`](build/infra/README.md)) creates the instance and its Cloud Firewall
and passes the instance cloud-init user data, rendered from
[`src/deploy/cloud-init.yaml.tftpl`](src/deploy/cloud-init.yaml.tftpl).

1. **First boot.** The stock Ubuntu 24.04 image has no NVIDIA driver and no CUDA. cloud-init
   installs NVIDIA's open driver (branch pinned), Docker Engine and the NVIDIA Container Toolkit,
   clones this repository at `repo_ref` into `/opt/sys1`, enables `sys1-bringup.service`, and
   reboots once to load the driver. The OpenJev images bring their own CUDA 13.
2. **Every boot after that.** `sys1-bringup.service` runs
   [`src/deploy/bringup.sh`](src/deploy/bringup.sh): it checks the GPU, pulls OpenJev's two
   images, downloads both checkpoints pinned by revision, then starts
   [`compose.yaml`](src/deploy/compose.yaml), which builds the app's image on the host from this
   repository. Last, it asks each model one question through the app and logs the decision.

**Push first.** The host clones this repository at `repo_ref`, so whatever that ref holds is
what it builds. There is no image registry.

## How the settings get there

Terraform variables → user data → `/etc/sys1.env` on the host → the containers, through
`docker compose --env-file /etc/sys1.env`. The file holds the app's port, the OpenJev image tag
and the two checkpoints with their revisions. There are no secrets: OpenJev runs without a key,
both checkpoints are public, and your Linode API token stays in your shell, never on the host.

## Deploy

You need Terraform, an Akamai account that can deploy the plan, an API token and an SSH key.

```sh
cd build/infra
cp terraform.tfvars.example terraform.tfvars  # ignored by git
export LINODE_TOKEN=...                        # read by the provider, never stored
terraform init
terraform apply
```

In `terraform.tfvars`, set `region` and `plan` to ones your account can deploy, your
`ssh_public_key`, `allowed_cidrs` (below), and `repo_url` and `repo_ref` for your push of this
repository. The module's inputs and outputs are in [`build/infra/README.md`](build/infra/README.md).

## Watch the bring-up

```sh
$(terraform output -raw bringup_command)   # ssh root@<ip> tail -F /var/log/cloud-init-output.log
```

Each phase prints a `sys1:` line with a UTC time: the driver, Docker, the toolkit, the clone and
the reboot (your SSH session drops; run the command again), then `driver`, `images`, `weights`,
`stack`, three `decision` lines and `ready`. The first start of `openjev` loads 19 GB of weights
and compiles GPU kernels; `docker logs -f sys1-openjev-1` shows it. ASSUMPTION (unverified): the
whole bring-up takes tens of minutes; it has not been measured, and the timestamps measure it.

If a step fails, the log names its phase. Before the reboot, the host stays up unrebooted:
replace it with `terraform apply -replace=linode_instance.gpu_host`. After it, fix the cause and
run `systemctl restart sys1-bringup`.

- ASSUMPTION (unverified): that `openjev`'s first start fits in the 30 minutes its health check
  allows. If it does not, the `stack` phase fails; once `docker logs sys1-openjev-1` shows it
  serving, run `systemctl restart sys1-bringup`.
- The driver's reboot is the instance's own, and relies on Akamai's shutdown watchdog, Lassie, to
  boot it back up. ASSUMPTION (unverified): that Lassie does so for this one-card plan; Akamai
  notes it may not reboot Blackwell instances after a shutdown, mostly multi-GPU ones
  ([known limitations](https://techdocs.akamai.com/cloud-computing/docs/known-limitations-you-may-encounter-with-nvidia-rtx-pro-6000-blackwell-server-edition-gpu-linodes),
  as of 2026-10-02). If the host stays off, boot it from Cloud Manager; the boot-time service
  carries on.

## Open the page and ask

Open `terraform output -raw url` (plain HTTP, no domain). The Cloud Firewall admits only the
page's port and SSH, and only from `allowed_cidrs`; no model server publishes a port, so from
anywhere else nothing answers.

Pick a sample text and a preset (routing, a smart if-statement, a guardrail), choose DiffusionGemma,
Laya on the GPU or Laya on the CPU, and ask. Each answer shows three legs: OpenJev's own time,
the app's hop to OpenJev, and the browser's round trip to the app. Ask one preset of Laya on both
devices to see what the GPU buys.

## Changing a running deployment

- `terraform apply` again with unchanged inputs changes nothing.
- A new `repo_ref`, a new SSH key, or anything else rendered into the user data **replaces the
  host**: a new URL, a fresh bring-up, and a fresh request for GPU capacity.
- Firewall rules, the allowed range among them, update in place.
- To change the app on a running host, push, then run
  `ssh root@<ip> bash /opt/sys1/src/deploy/update.sh <ref>`. It rebuilds and restarts only the
  app; the models keep running.

## From rehearsal through the talk

- **Cost.** About $72 a day at the listed price. A GPU instance bills hourly even when powered
  off ([billing](https://techdocs.akamai.com/cloud-computing/docs/understanding-how-billing-works),
  as of 2026-09-29), so off means destroyed: destroy it after the talk.
- **Change only the allowed range.** It updates in place; anything else may replace the host.
- **The range is the presenter's browser egress**, as the internet sees it; a VPN changes it.
- **Reboot from Cloud Manager, never from the shell.** If the driver's reboot during bring-up
  leaves the host off, boot it from Cloud Manager and the boot-time service resumes.
- **Check scheduled maintenance first.** GPU passthrough rules out live migration, so a
  maintenance event restarts the host.

## Back to zero cost

```sh
terraform destroy
```

Then confirm in Cloud Manager that the Linode and the Cloud Firewall labelled `sys1-inference`
are gone. GPU deletions can lag: Akamai asks for a support ticket if one has not finished after
five minutes. Nothing outside the module bills: no volumes, buckets, registry or DNS.

## Tests

`uv run pytest` tests the app against a stand-in OpenJev, and checks the bootstrap: Terraform
renders the template from the module's example variables, `cloud-init schema` validates it, and
the tests confirm the pinned image tag and revisions and the single published port. Checks that
need `terraform` or `cloud-init` skip where those are not installed.
