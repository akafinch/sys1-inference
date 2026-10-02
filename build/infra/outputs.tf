# Values populate after apply. The public address comes from the instance's `ipv4` set:
# provider 4.7.0 deprecates `ip_address`.

locals {
  # The instance requests no private IP, so its ipv4 set holds only the public address; one()
  # fails loudly if it ever holds more [the provider's deprecation notice for ip_address names the
  # ipv4 set, `terraform validate` with linode/linode 4.7.0, 2026-10-01].
  public_ipv4 = one(linode_instance.gpu_host.ipv4)
}

output "url" {
  description = "The demo page. Plain HTTP, no domain."
  value       = var.app_port == 80 ? "http://${local.public_ipv4}/" : "http://${local.public_ipv4}:${var.app_port}/"
}

output "ipv4" {
  description = "The host's public IPv4 address, from the instance's ipv4 set."
  value       = local.public_ipv4
}

output "bringup_command" {
  description = "Watch bring-up over SSH: the bootstrap's phases in the cloud-init log."
  # cloud-init's output log; after the driver reboot, the bring-up service appends its phases to
  # the same file (src/deploy/bringup.sh).
  value = "ssh root@${local.public_ipv4} tail -F /var/log/cloud-init-output.log"
}

output "instance_id" {
  description = "Linode ID, for Cloud Manager and for confirming teardown."
  value       = linode_instance.gpu_host.id
}

output "firewall_id" {
  description = "Cloud Firewall ID."
  value       = linode_firewall.this.id
}
