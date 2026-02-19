# Deployment configuration notes

## Open vSwitch provider bridge fail mode

Set `ovs_provider_fail_mode` explicitly in `globals.yml` for production deployments.
Do not rely on the role default.

Recommended production value:

```yaml
ovs_provider_fail_mode: "secure"
```

Allowed values are:

- `secure`
- `standalone`

When this is set explicitly, provider bridge fail mode handling is deterministic
across upgrades and rebases.
