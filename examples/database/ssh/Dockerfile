# An OpenSSH server (BSD) for testing doctracker's SSH tunnels: one user, `tunnel`, logging in only with
# the test key mounted at /etc/ssh/authorized_keys/tunnel, allowed to forward ports and nothing else.
FROM alpine:3.20
RUN apk add --no-cache openssh-server \
 && ssh-keygen -A \
 && adduser -D -s /bin/sh tunnel \
 && sed -i 's/^tunnel:!/tunnel:*/' /etc/shadow \
 && printf '%s\n' \
      'PasswordAuthentication no' 'KbdInteractiveAuthentication no' 'PermitRootLogin no' \
      'AuthorizedKeysFile /etc/ssh/authorized_keys/%u' 'StrictModes no' \
      'AllowTcpForwarding yes' 'GatewayPorts no' 'X11Forwarding no' 'PermitTTY no' \
      > /etc/ssh/sshd_config.d/tunnel.conf
EXPOSE 22
CMD ["/usr/sbin/sshd", "-D", "-e"]
