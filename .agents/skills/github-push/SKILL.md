---
name: github-push
description: Handles the complete Git workflow for initializing repositories, configuring GitHub accounts, inspecting changes, synchronizing branches, staging, committing and pushing code. Use whenever the user wants to initialize a Git repository, connect a GitHub repository, or commit and push code.
---

# GitHub Push Skill

## 1. Objective

Automate the complete Git workflow for the current project.

The user will provide three inputs:

1. GitHub repository URL
2. Target branch name
3. GitHub account: personal or work

Example:

Repository URL: git@github.com:company/payment-service.git
Branch: feature/payment-retry
Account: work

Do not ask for information that can be determined by inspecting the repository.

If any mandatory input is missing, ask the user.

---

## 2. GitHub Account Configuration

Two GitHub accounts are configured in the user's SSH config.

### Personal Account

- Account: personal
- Git author name: Vishal Singh
- Git author email: iamvishal.2811@gmail.com
- SSH alias: github-personal
- SSH HostName: github.com
- SSH User: git
- SSH Key: ~/.ssh/id_ed25519_personal

### Work Account

- Account: work
- Git author name: Vishal Singh
- Git author email: vishals@yodaplus.com
- SSH alias: github-work
- SSH HostName: github.com
- SSH User: git
- SSH Key: ~/.ssh/id_ed25519_work

### Mandatory Account Mapping Rules

The account input determines BOTH Git identity and SSH authentication.

| Account | Git user.email | SSH alias |
|---|---|---|
| personal | iamvishal.2811@gmail.com | github-personal |
| work | vishals@yodaplus.com | github-work |

Never interchange these mappings.

### Git Configuration

Always configure the identity locally for the current repository.

For personal:

git config --local user.name "Vishal Singh"
git config --local user.email "iamvishal.2811@gmail.com"

For work:

git config --local user.name "Vishal Singh"
git config --local user.email "vishals@yodaplus.com"

### Verification

Before committing, verify:

git config --local user.name
git config --local user.email

The email MUST match the selected account.

If it does not match, correct it before committing.

Never use git config --global.

Never ask the user to provide an email because both account emails are already configured here.


## 3. Input Validation

Validate all three inputs.

### Repository URL

Accept:
- HTTPS GitHub URLs
- Standard SSH GitHub URLs
- SSH alias URLs

Normalize the URL to the selected SSH alias.

Examples:

Personal:
git@github-personal:OWNER/REPO.git

Work:
git@github-work:OWNER/REPO.git

Preserve the original repository owner and name.

Never silently change the destination repository.

If the supplied URL points to a different hosting provider, stop and ask.

### Branch

- Branch name must be explicitly supplied.
- Never assume main or master.
- Validate the branch name.
- Use the supplied branch throughout the workflow.
- Never silently switch to another branch.

### Account

Only accept:
- personal
- work

If another value is supplied, ask for clarification.

---

## 4. Repository Discovery

Start by inspecting the current working directory.

Execute:

git rev-parse --show-toplevel

git status --short --branch

git remote -v

git branch -avv

git log -5 --oneline

Determine:

- Whether Git is initialized.
- Whether the current directory is already inside a Git repository.
- Whether the repository has an origin remote.
- Whether the existing remote matches the supplied URL.
- Whether local branches exist.
- Whether uncommitted changes exist.
- Whether the repository contains previous commits.

Never initialize a nested Git repository inside an existing repository.

If the current directory is not the intended project directory, stop and clarify.

---

## 5. Git Initialization

If Git is not initialized:

1. Run git init.
2. Configure account-specific local Git identity.
3. Add the supplied GitHub repository as origin.

Example:

git init

git config --local user.name "NAME"

git config --local user.email "EMAIL"

git remote add origin git@github-work:OWNER/REPO.git

Do not overwrite existing files or project contents.

If Git is already initialized:

- Preserve existing repository history.
- Inspect existing remotes.
- Verify the supplied repository URL.
- Update origin only when the existing repository is clearly intended to point to the supplied destination.

If the existing origin points to an unrelated repository, ask before changing it.

---

## 6. Branch Management

Fetch remote information:

git fetch origin --prune

Check whether the supplied branch exists locally or remotely.

### Case A: Branch exists locally

Switch to the supplied branch:

git switch BRANCH

Only switch if doing so will not overwrite uncommitted changes.

### Case B: Branch exists remotely but not locally

Create a tracking branch:

git switch --track -c BRANCH origin/BRANCH

### Case C: Branch does not exist locally or remotely

Create it:

git switch -c BRANCH

Never delete, overwrite or recreate an existing branch.

If switching branches could overwrite uncommitted work, stop and ask.

---

## 7. Complete Working Tree Analysis

Inspect the entire working tree before deciding what to commit.

Execute:

git status --short --branch

git diff

git diff --cached

git ls-files --others --exclude-standard

git diff HEAD

Inspect relevant changed file contents.

Classify changes into:

- Modified files
- New files
- Deleted files
- Renamed files
- Staged changes
- Unstaged changes
- Untracked files
- Generated files
- Configuration changes
- Unrelated changes

Check ignored files when relevant:

git status --ignored --short

### Change Understanding

Understand the purpose of each relevant change.

Determine:

- What functionality has changed?
- Which files belong together?
- Are there incomplete implementations?
- Are there accidental changes?
- Are there generated files?
- Are there sensitive files?
- Are there unrelated changes?

Do not blindly commit every file in the project.

If unrelated changes or ambiguous commit scope exist, ask the user which changes to include.

---

## 8. Security and File Exclusions

Before staging, inspect files for potentially sensitive content.

Never commit:

- Private SSH keys.
- API keys.
- Access tokens.
- Passwords.
- Credentials.
- Secret environment files.
- Database connection strings containing credentials.

Pay particular attention to:

.env
.env.local
*.pem
*.key
id_rsa
id_ed25519

Also check for:

- Build directories.
- Cache directories.
- Temporary files.
- Large generated artifacts.
- Dependency directories.

Respect .gitignore.

Do not modify .gitignore automatically unless necessary and authorized.

Never stage sensitive files even if they are already tracked without first informing the user.

---

## 9. Remote Synchronization

Fetch the latest remote information:

git fetch origin

Check whether the target branch exists remotely.

If it exists, compare local and remote history:

git rev-list --left-right --count HEAD...origin/BRANCH

Determine whether the branch is:

- In sync
- Ahead
- Behind
- Diverged

### If the local branch is behind

If the working tree is clean:

git pull --rebase origin BRANCH

### If the branch has diverged

Do not automatically rewrite published history.

Inspect the commits on both sides.

Choose a safe synchronization strategy only when the intended outcome is clear.

Ask the user if the reconciliation strategy is ambiguous.

### If there are uncommitted changes

Do not run pull commands that could overwrite those changes.

Preserve all local work.

When necessary, commit the intended changes first and then rebase onto the latest remote branch before pushing.

Never discard changes to make a pull succeed.

### Conflict Handling

If conflicts occur:

1. Identify conflicting files.
2. Inspect both versions.
3. Understand the intended changes.
4. Resolve only if the correct result is clear.
5. Otherwise ask the user.

Never use reset --hard or checkout commands that discard changes.

---

## 10. Staging Changes

Stage only relevant files.

Prefer selective staging:

git add file1 file2

Do not blindly execute:

git add .

After staging, inspect:

git status --short

git diff --cached --stat

git diff --cached

Verify:

- All intended files are staged.
- No unrelated changes are staged.
- No secrets are staged.
- Deleted files are intentional.
- New files are relevant.
- The staged diff matches the intended commit.

If partial changes within a file need to be staged, use interactive staging where practical.

Do not stage additional files without understanding their contents.

---

## 11. Commit Message Generation

Analyze the staged diff and generate a meaningful commit message.

Prefer conventional commit style:

feat: add payment retry mechanism

fix: handle null API responses

refactor: simplify repository initialization

docs: update API documentation

test: add payment validation tests

Rules:

- Keep messages concise.
- Describe actual changes.
- Do not invent functionality.
- Do not use generic messages such as update or changes.
- Use the appropriate commit type.

---

## 12. Commit

Before committing, perform a final staged-diff review.

Execute:

git commit -m "GENERATED_COMMIT_MESSAGE"

Do not create empty commits.

If there is nothing meaningful to commit, report that no commit is necessary.

Never amend existing commits unless explicitly requested.

---

## 13. SSH Authentication

Verify authentication using the selected account.

For personal:

ssh -T git@github-personal

For work:

ssh -T git@github-work

Verify that GitHub identifies the expected account.

GitHub SSH authentication can return a non-zero exit code even when authentication succeeds. Inspect the actual response.

If authentication fails or the account is incorrect:

- Stop the workflow.
- Do not attempt the push.
- Report the problem.

Never modify SSH configuration or regenerate keys.

---

## 14. Push Changes

Before pushing:

- Verify origin.
- Verify the target branch.
- Verify account identity.
- Verify the latest remote history.
- Ensure there are no unresolved conflicts.

If the branch has an upstream:

git push

Otherwise:

git push -u origin BRANCH

Never use:

git push --force

git push --force-with-lease

unless explicitly authorized by the user.

If the remote has advanced since the last fetch, fetch and synchronize safely before retrying.

---

## 15. Post-Push Verification

After pushing, execute:

git status --short --branch

git log -1 --oneline

git ls-remote origin refs/heads/BRANCH

Verify:

- The push succeeded.
- The remote branch exists.
- The remote commit matches the expected local commit.
- The working tree is clean or remaining changes are clearly reported.
- The correct GitHub account was used.

Do not claim success if verification fails.

---

## 16. Safety Rules

1. Never modify ~/.ssh/config.
2. Never generate or overwrite SSH keys.
3. Never expose private key contents.
4. Never modify global Git configuration.
5. Never overwrite an unrelated Git remote.
6. Never discard uncommitted changes.
7. Never silently switch branches.
8. Never force-push without explicit authorization.
9. Never commit secrets or credentials.
10. Never commit unrelated changes.
11. Never resolve ambiguous conflicts automatically.
12. Never claim a successful push without verification.
13. Preserve existing repository history.
14. Ask before destructive or ambiguous operations.

---

## 17. Final Execution Report

After completing the workflow, provide a concise report.

Include:

### Repository
- Repository URL
- Git initialization status
- Account used

### Branch
- Target branch
- Previous branch, if changed
- Remote synchronization status

### Changes
- Files added
- Files modified
- Files deleted
- Files excluded and reasons

### Commit
- Commit message
- Commit hash
- Number of files committed

### Push
- Push result
- Remote branch
- Remote commit verification

### Final Status
- Working tree clean or dirty
- Remaining uncommitted changes
- Any warnings or unresolved issues

Do not hide errors or warnings.
