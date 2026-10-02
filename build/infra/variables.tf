# Two kinds of input:
#   - project-wide values, the same in every environment, arrive in adp.auto.tfvars.json;
#   - per-environment values (region, plan, access) are plain variables for the operator,
#     set in terraform.tfvars (see terraform.tfvars.example).

# ── project-wide (adp.auto.tfvars.json) ──────────────────────────────────────────────

variable "image" {
  description = "Base image."
  type        = string
}

variable "interface_generation" {
  description = "Network interface generation, set explicitly rather than left to the account's default."
  type        = string
}

variable "openjev_version" {
  description = "Tag of both OpenJev images. Never latest."
  type        = string

  validation {
    condition     = var.openjev_version != "latest"
    error_message = "openjev_version must be a pinned tag, never latest."
  }
}

variable "diffusiongemma_model" {
  description = "DiffusionGemma checkpoint, served as OpenJev's openjev-0.1."
  type        = string
}

variable "diffusiongemma_revision" {
  description = "DiffusionGemma checkpoint revision."
  type        = string
}

variable "laya_model" {
  description = "Laya checkpoint, served on GPU and on CPU."
  type        = string
}

variable "laya_revision" {
  description = "Laya checkpoint revision."
  type        = string
}

# ── per-environment (terraform.tfvars) ───────────────────────────────────────────────

variable "region" {
  description = "Akamai region. The demo's is us-sea; choose one where your account can deploy the plan."
  type        = string
  default     = "us-sea"
}

variable "plan" {
  description = "Linode type: one RTX PRO 6000 Blackwell card. Visible only to accounts granted Blackwell access."
  type        = string
  default     = "g3-gpu-rtxpro6000-blackwell-1"
}

variable "label" {
  description = "Label for the instance and its firewall."
  type        = string
  default     = "sys1-inference"
}

variable "ssh_public_key" {
  description = "SSH public key for root. Changing it replaces the host (authorized_keys is ForceNew)."
  type        = string
}

variable "allowed_cidrs" {
  description = "IPv4 ranges (CIDR) admitted to the page's port and SSH: the presenter's browser egress."
  type        = list(string)

  validation {
    condition     = length(var.allowed_cidrs) > 0 && alltrue([for c in var.allowed_cidrs : can(cidrhost(c, 0))])
    error_message = "allowed_cidrs must hold at least one valid IPv4 CIDR. There is no open default."
  }
}

variable "repo_url" {
  description = "Public git URL of this repository, which the host clones and builds the app from."
  type        = string
}

variable "repo_ref" {
  description = "Git ref the first boot builds. Changing it re-renders user data and replaces the host; update in place with src/deploy/update.sh instead."
  type        = string
}

variable "app_port" {
  description = "Port the app binds and the firewall opens."
  type        = number
  default     = 80
}

variable "nvidia_driver_branch" {
  description = "Open NVIDIA driver branch to pin. Must be 580 or newer for the images' CUDA 13."
  type        = string
  # NVIDIA's ubuntu2404 repository carries nvidia-open for branches 560 to 615, and pinning
  # packages from 570 [https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/,
  # as-of 2026-10-02].
  default = "595"
}
