# Seccomp provenance

Source profile: https://raw.githubusercontent.com/moby/profiles/main/seccomp/default.json
Upstream SHA256 recorded in the prior local deployment:
`3320527d4568265ac97a077609b1bfd4cfd0d789eeb9239b7e094b1526675406`.

AgentBox copied only the non-secret policy file from the prior installation;
no original file was modified. The existing policy permits clone, setns,
unshare and chroot for Chromium's nested sandbox. All other inherited
upstream rules remain. AgentBox file SHA256:
`565d3d64372a12f0b147eb59e8a221ecdf2e463cf1d500303d3e928f982080de`.

The application's original namespace retains UID 1000, no-new-privileges
and zero capability bounding set. A nested user namespace does not confer
NET_ADMIN in its parent's network namespace. This broadens kernel attack
surface and is not a guarantee against kernel vulnerabilities.

Gateway and relay use Docker's default seccomp profile. No unconfined
seccomp/systempaths, SYS_ADMIN, privileged or host namespace is used.
