# No runtime of its own: the persona and the three skills copied below are the
# tracked files this repo owns. Build context is the repo root: `docker build .`
#
# The tag is an immutable `base-<sha>` naming one commit of plow-pbc/plow-hermes-agent,
# pinned by digest as well. Never move it: every tenant VM inherits this exact
# filesystem while holding that owner's Plow credential, so a moving tag would
# substitute code underneath them. Bumping it is an edit somebody reviews.
FROM public.ecr.aws/e1h7x4a2/plow-cloud-agents:base-cd2a898d673812621bae6764560e455807e9818e@sha256:bfd4980f361a551e62569f8c2eb717c1076d0b8be3a0499b869eaece151336a4

# Replaces the base's own SOUL.md. First boot re-asserts root ownership on that
# file, which is what the trailing chmod answers.
COPY runtime/SOUL.md /var/lib/hermes/SOUL.md
COPY LICENSE /usr/share/doc/hermes-daily-tech-brief/

# Shipped at /opt/hermes/skills, outside every home, so a bind-mounted home
# still receives them and an image update still reaches an uncustomised skill,
# both through the base runtime's reconcile.
COPY tb-brief/     /opt/hermes/skills/tb-brief/
COPY tb-setup/     /opt/hermes/skills/tb-setup/
COPY tb-schedule/  /opt/hermes/skills/tb-schedule/

# Normalise whatever modes the checkout carried, preserving the executable bit:
# the skill sheets invoke scripts by path, so a blanket 0644 makes them fail
# with Permission denied.
# -mindepth 1: the skills root is the base's, root-owned and sticky, and
# recursing over it would leave it unwritable for the gateway's own bundled
# skill install.
RUN find /opt/hermes/skills -mindepth 1 -type d -exec chmod 0755 {} + \
 && find /opt/hermes/skills -mindepth 1 -type f ! -perm -u+x -exec chmod 0644 {} + \
 && find /opt/hermes/skills -mindepth 1 -type f -perm -u+x -exec chmod 0755 {} + \
 && chmod 0644 /var/lib/hermes/SOUL.md

# The usage reporter, fetched at build from the commit vendor/client.pin names
# and checked against the hash beside it. Fetched rather than committed because
# plow-pbc/agent-index-client owns that file; pinned rather than tracked from a
# branch because this runs inside an agent holding a live credential.
# The checksum is the second half: a sha in a URL is only as good as the host
# serving it.
#
# Root-owned under /opt/plow on purpose. Everything under $HERMES_HOME belongs
# to uid 10000 in a running container, so scheduling a copy that lives there
# would turn one prompt-injected edit into code that runs unattended, forever,
# holding a live credential. The agent can read this one and cannot change it.
COPY vendor/client.pin /opt/plow/agent-index-client.pin
RUN set -eu; \
    sha="$(sed -n 's/^sha=//p' /opt/plow/agent-index-client.pin)"; \
    want="$(sed -n 's/^sha256=//p' /opt/plow/agent-index-client.pin)"; \
    path="$(sed -n 's/^path=//p' /opt/plow/agent-index-client.pin)"; \
    curl -fsS --max-time 60 -o /opt/plow/agent-index-client.py \
      "https://raw.githubusercontent.com/plow-pbc/agent-index-client/${sha}/${path}"; \
    got="$(sha256sum /opt/plow/agent-index-client.py | cut -d' ' -f1)"; \
    [ "$got" = "$want" ] || { echo "agent-index client is $got, pin says $want" >&2; exit 1; }; \
    chmod 0644 /opt/plow/agent-index-client.py

COPY image/s6-overlay/ /etc/s6-overlay/

RUN find /etc/s6-overlay/s6-rc.d -type f -name run -exec chmod 0755 {} +

# The instance directory the brief reads and tb-setup writes. Nothing exists
# before first boot, so the image creates it empty: an unconfigured agent is
# routed to tb-setup by SOUL.md.
RUN install -d -o 10000 -g 10000 -m 0700 /var/lib/hermes/tb