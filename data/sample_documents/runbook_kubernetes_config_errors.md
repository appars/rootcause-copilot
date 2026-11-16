# Runbook: Pods that will not start after a deployment (FICTIONAL - training material)

## Symptoms
- `CreateContainerConfigError`
- `configmap "<name>" not found` or `secret "<name>" not found`
- Application errors such as `Could not resolve placeholder` / `missing required property`
- Readiness probe failures and `Back-off restarting failed container`
- Rollout stuck: `0/N replicas available` while the old ReplicaSet keeps serving

## Investigation steps
1. `kubectl describe pod <pod>` - read the Events section.
2. Compare the ConfigMap/Secret names referenced in the Deployment (`envFrom`, `env.valueFrom`,
   `volumes`) with what exists: `kubectl get configmap,secret -n <namespace>`.
3. Check whether the configuration change was committed to the GitOps repository and synced.
4. Check the application's required settings for the new version (release notes).

## Mitigation options (via Git + ArgoCD; approval required)
- Add the missing ConfigMap/Secret (Secrets are created outside Git) and re-sync.
- Fix the reference in the Deployment.
- `git revert` the release commit so ArgoCD rolls back to the last good version.

## Prevention
- Validate manifests in CI (e.g. schema checks, reference checks) before merging.
- Deploy configuration before (or together with) the code that depends on it.
