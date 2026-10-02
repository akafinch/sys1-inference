# One Akamai GPU instance and the Cloud Firewall in front of it (checked 2026-10-01).
#
# What it creates:
#   gpu-host     -> linode_instance
#   firewall     -> linode_firewall, attached by the instance's firewall_id
#   model-server -> no resource of its own: containers on gpu-host, started by the
#                   bootstrap that src/deploy/ renders

resource "linode_firewall" "this" {
  label = var.label

  # Rules update in place; no firewall attribute forces the firewall's replacement
  # [https://github.com/linode/terraform-provider-linode/tree/v4.7.0/linode/firewall, as-of 2026-10-01].
  inbound {
    label    = "page"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = tostring(var.app_port)
    ipv4     = var.allowed_cidrs
  }

  inbound {
    label    = "ssh"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = "22"
    ipv4     = var.allowed_cidrs
  }

  inbound_policy  = "DROP"
  outbound_policy = "ACCEPT" # images, weights and the repository come from the internet

  # Do NOT list the instance in `linodes`: it attaches once, at creation, through the
  # instance's firewall_id.
}

resource "linode_instance" "gpu_host" {
  label  = var.label
  region = var.region
  type   = var.plan
  image  = var.image

  # Set explicitly, never left to the account default, so the firewall_id attachment below is
  # valid whichever generation an account defaults to [interface_generation, `legacy_config` |
  # `linode`, default from the account's interfaces_for_new_linodes:
  # https://registry.terraform.io/providers/linode/linode/latest/docs/resources/instance, as-of 2026-10-01].
  interface_generation = var.interface_generation

  # Attached at creation, so the host never boots unfirewalled. ForceNew [same page].
  firewall_id = linode_firewall.this.id

  # ForceNew: changing the key replaces the host [same page].
  authorized_keys = [trimspace(var.ssh_public_key)]

  metadata {
    # The bootstrap is cloud-init user data, base64-encoded [same page, metadata.0.user_data].
    # user_data is ForceNew [linode/instance/schema_resource.go at v4.7.0, as-of 2026-10-01]:
    # anything rendered here (notably repo_ref) replaces the host when it changes.
    # The template lives in src/deploy/, beside this module.
    user_data = base64encode(templatefile("${path.module}/../../src/deploy/cloud-init.yaml.tftpl", {
      repo_url                = var.repo_url
      repo_ref                = var.repo_ref
      app_port                = var.app_port
      openjev_version         = var.openjev_version
      diffusiongemma_model    = var.diffusiongemma_model
      diffusiongemma_revision = var.diffusiongemma_revision
      laya_model              = var.laya_model
      laya_revision           = var.laya_revision
      nvidia_driver_branch    = var.nvidia_driver_branch
    }))
  }
}
