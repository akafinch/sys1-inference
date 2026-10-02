# Infrastructure module

Terraform for one Akamai GPU instance and its Cloud Firewall. Nothing here runs `apply` on its own:
you do, and the instance bills from that moment.

| Resource | Provider | Terraform |
|---|---|---|
| `gpu-host` | Akamai | `linode_instance.gpu_host` |
| `firewall` | Akamai | `linode_firewall.this`, attached by the instance's `firewall_id` |
| `model-server` | self-hosted | none: OpenJev runs in containers on `gpu-host`, started by the bootstrap |

**Inputs.** `adp.auto.tfvars.json` carries the project-wide values, the same in every environment:
the image, the interface generation, the OpenJev tag, and the checkpoints with their revisions.
Per-environment values (region, plan, SSH key, allowed ranges, repository and ref) are plain
variables: copy `terraform.tfvars.example` to `terraform.tfvars`. The token is read from
`LINODE_TOKEN`.

**Outputs.** `url`, `ipv4`, `bringup_command`, `instance_id`, `firewall_id`.

**The bootstrap** is `src/deploy/cloud-init.yaml.tftpl`. `main.tf` renders it with exactly these
variables: `repo_url`, `repo_ref`, `app_port`, `openjev_version`, `diffusiongemma_model`,
`diffusiongemma_revision`, `laya_model`, `laya_revision`, `nvidia_driver_branch`.

## Evidence

- Provider `linode/linode` 4.7.0, current as of 2026-10-01 (published 2026-09-29), pinned `~> 4.7`
  [https://registry.terraform.io/providers/linode/linode/latest/docs].
- `interface_generation` (`legacy_config` | `linode`; the default comes from the account),
  `firewall_id` (ForceNew), `authorized_keys` (ForceNew), `metadata.user_data` (base64), and the
  `ipv4` set [https://registry.terraform.io/providers/linode/linode/latest/docs/resources/instance,
  as-of 2026-10-01]. `ip_address` is deprecated in 4.7.0, so the outputs read `ipv4` instead
  [`terraform validate`, 2026-10-01]. `user_data` is ForceNew [linode/instance/schema_resource.go at v4.7.0, as-of 2026-10-01].
- Firewall rules (`inbound`, `inbound_policy`, `outbound_policy`) update in place
  [https://registry.terraform.io/providers/linode/linode/latest/docs/resources/firewall; v4.7.0 `linode/firewall/`, as-of 2026-10-01].
- The plan id `g3-gpu-rtxpro6000-blackwell-1` and its $3.00 an hour are visible only with a token
  from an account that has Blackwell access: checked against our account on 2026-09-30; check yours.
- `linode/ubuntu24.04` supports cloud-init in us-sea [Linode API `GET /v4/regions/us-sea` and
  `GET /v4/images/linode/ubuntu24.04`, as-of 2026-10-01].
- Driver branch default `595`: NVIDIA's ubuntu2404 repository carries `nvidia-open` for branches
  560 to 615, and pinning packages from 570
  [https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/, as-of 2026-10-02].
- ASSUMPTION (unverified): the `required_version` floor of 1.5.
