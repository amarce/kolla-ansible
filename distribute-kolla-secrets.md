# Distributing Kolla Secrets

This feature allows administrators to organise service specific secret files on
the deploy host and automatically distribute them to the correct hosts during
`kolla-ansible bootstrap-servers`, `deploy`, `deploy-containers`,
`reconfigure` and `upgrade`.

## Organising Secrets

On the deploy host place files under `/etc/kolla/config/secrets/<group>/` where
`<group>` matches an inventory group name. All files in such a directory will be
copied to `/etc/kolla/secrets/<group>/` on hosts belonging to that group.
Secret directories can be mapped to multiple inventory groups via the
`kolla_secrets_group_map` variable when the directory name does not match the
group.

Example:

```text
/etc/kolla/config/secrets/nova/gitlab_key.pub
```

After running any of the above commands the file will be available on all hosts
in the `nova` group as:

```text
/etc/kolla/secrets/nova/gitlab_key.pub
```

## Integration with kolla-ansible

No additional commands are required. When the listed commands run they now call
an additional role that performs the distribution. The destination directory is
created with `0700` permissions and files default to `0644`. More restrictive
source permissions such as `0600` are preserved. The distribution may also be
triggered manually using `kolla-ansible distribute-secrets`.

Empty directories are skipped with a debug message and directories that do not
exist are silently ignored. The tasks are idempotent and safe to run multiple
times.

## Security and Idempotency

Secrets should be readable only by the deploy user and stored securely. Ensure
the `/etc/kolla/config/secrets/` hierarchy on the deploy host is protected. Logs
provide information about which groups and files were processed. Because the
copy operation is idempotent it may be executed safely in CI environments.
