# Autonomous Coding Agent Demo

A minimal harness demonstrating long-running autonomous coding with the Claude Agent SDK. This demo implements a two-agent pattern (initializer + coding agent) that can build complete applications over multiple sessions.

## Prerequisites

**Required:** Install the latest versions of both Claude Code and the Claude Agent SDK:

```bash
# Install Claude Code CLI (latest version required)
npm install -g @anthropic-ai/claude-code

# Install Python dependencies
pip install -r requirements.txt
```

Verify your installations:
```bash
claude --version  # Should be latest version
pip show claude-code-sdk  # Check SDK is installed
```

**Authentication:** Configure authentication (choose one method):

```bash
# Option 1: Anthropic API Key
export ANTHROPIC_API_KEY='your-api-key-here'

# Option 2: AWS Bedrock (via Claude Code config)
# Ensure ~/.claude/settings.json has:
# - awsCredentialExport: path to AWS credential script
# - CLAUDE_CODE_USE_BEDROCK=1
# - Bedrock model IDs
```

## Quick Start

```bash
python autonomous_agent_demo.py --project-dir ./my_project
```

For testing with limited iterations:
```bash
python autonomous_agent_demo.py --project-dir ./my_project --max-iterations 3
```

## Important Timing Expectations

> **Warning: This demo takes a long time to run!**

- **First session (initialization):** The agent generates a `feature_list.json` with 200 test cases. This takes several minutes and may appear to hang - this is normal. The agent is writing out all the features.

- **Subsequent sessions:** Each coding iteration can take **5-15 minutes** depending on complexity.

- **Full app:** Building all 200 features typically requires **many hours** of total runtime across multiple sessions.

**Tip:** The 200 features parameter in the prompts is designed for comprehensive coverage. If you want faster demos, you can modify `prompts/initializer_prompt.md` to reduce the feature count (e.g., 20-50 features for a quicker demo).

## Authentication Methods

The autonomous agent supports two authentication methods via Claude Code CLI:

### 1. Anthropic API Key (Default)

Set the `ANTHROPIC_API_KEY` environment variable:

```bash
export ANTHROPIC_API_KEY='your-api-key-here'
```

Get your API key from: https://console.anthropic.com/

### 2. AWS Bedrock

Configure `~/.claude/settings.json` with Bedrock settings:

```json
{
  "awsCredentialExport": "/path/to/aws-credential-script.sh",
  "env": {
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "AWS_REGION": "us-west-2"
  }
}
```

Requirements:
- AWS credentials configured (via AWS SSO or IAM)
- Access to Claude models in Amazon Bedrock
- Credential export script that outputs AWS STS credentials

Example credential script (`generate_aws_claude_grant.sh`):
```bash
#!/bin/bash
PROFILE="your-aws-profile"

# Refresh credentials if expired
aws sts get-caller-identity --profile "$PROFILE" &>/dev/null
if [ $? -ne 0 ]; then
    aws sso login --profile "$PROFILE" >&2
fi

# Export credentials in STS format
CREDS=$(aws configure export-credentials --profile "$PROFILE" --format env-no-export 2>/dev/null)
eval "$CREDS"

cat <<EOF
{
  "Credentials": {
    "AccessKeyId": "$AWS_ACCESS_KEY_ID",
    "SecretAccessKey": "$AWS_SECRET_ACCESS_KEY",
    "SessionToken": "$AWS_SESSION_TOKEN"
  }
}
EOF
```

Make the script executable:
```bash
chmod +x /path/to/generate_aws_claude_grant.sh
```

**Note:** Use Bedrock model IDs when using Bedrock authentication:
- Regional: `us.anthropic.claude-sonnet-4-5-20250929-v1:0`
- Global: `global.anthropic.claude-sonnet-4-5-20250929-v1:0`

See [Claude on Amazon Bedrock](https://docs.anthropic.com/en/api/claude-on-amazon-bedrock) for details.

## How It Works

### Two-Agent Pattern

1. **Initializer Agent (Session 1):** Reads `app_spec.txt`, creates `feature_list.json` with 200 test cases, sets up project structure, and initializes git.

2. **Coding Agent (Sessions 2+):** Picks up where the previous session left off, implements features one by one, and marks them as passing in `feature_list.json`.

### Session Management

- Each session runs with a fresh context window
- Progress is persisted via `feature_list.json` and git commits
- The agent auto-continues between sessions (3 second delay)
- Press `Ctrl+C` to pause; run the same command to resume

## Security Model

This demo uses a defense-in-depth security approach (see `security.py` and `client.py`):

1. **OS-level Sandbox:** Bash commands run in an isolated environment
2. **Filesystem Restrictions:** File operations restricted to the project directory only
3. **Bash Allowlist:** Only specific commands are permitted:
   - File inspection: `ls`, `cat`, `head`, `tail`, `wc`, `grep`
   - Node.js: `npm`, `node`
   - Version control: `git`
   - Process management: `ps`, `lsof`, `sleep`, `pkill` (dev processes only)

Commands not in the allowlist are blocked by the security hook.

## Project Structure

```
autonomous-coding/
├── autonomous_agent_demo.py  # Main entry point
├── agent.py                  # Agent session logic
├── client.py                 # Claude SDK client configuration
├── security.py               # Bash command allowlist and validation
├── progress.py               # Progress tracking utilities
├── prompts.py                # Prompt loading utilities
├── prompts/
│   ├── app_spec.txt          # Application specification
│   ├── initializer_prompt.md # First session prompt
│   └── coding_prompt.md      # Continuation session prompt
└── requirements.txt          # Python dependencies
```

## Generated Project Structure

After running, your project directory will contain:

```
my_project/
├── feature_list.json         # Test cases (source of truth)
├── app_spec.txt              # Copied specification
├── init.sh                   # Environment setup script
├── claude-progress.txt       # Session progress notes
├── .claude_settings.json     # Security settings
└── [application files]       # Generated application code
```

## Running the Generated Application

After the agent completes (or pauses), you can run the generated application:

```bash
cd generations/my_project

# Run the setup script created by the agent
./init.sh

# Or manually (typical for Node.js apps):
npm install
npm run dev
```

The application will typically be available at `http://localhost:3000` or similar (check the agent's output or `init.sh` for the exact URL).

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--project-dir` | Directory for the project | `./autonomous_demo_project` |
| `--max-iterations` | Max agent iterations | Unlimited |
| `--model` | Claude model to use | `claude-sonnet-4-5-20250929` |

## Customization

### Changing the Application

Edit `prompts/app_spec.txt` to specify a different application to build.

### Adjusting Feature Count

Edit `prompts/initializer_prompt.md` and change the "200 features" requirement to a smaller number for faster demos.

### Modifying Allowed Commands

Edit `security.py` to add or remove commands from `ALLOWED_COMMANDS`.

## Troubleshooting

**"Appears to hang on first run"**
This is normal. The initializer agent is generating 200 detailed test cases, which takes significant time. Watch for `[Tool: ...]` output to confirm the agent is working.

**"Command blocked by security hook"**
The agent tried to run a command not in the allowlist. This is the security system working as intended. If needed, add the command to `ALLOWED_COMMANDS` in `security.py`.

**"Authentication failed"**
Check that you have configured authentication:
- Option 1: Set `ANTHROPIC_API_KEY` environment variable
- Option 2: Configure AWS Bedrock in `~/.claude/settings.json`
For Bedrock, ensure your AWS credentials are valid:
```bash
aws sts get-caller-identity --profile your-profile
```
Check Claude Code CLI can authenticate:
```bash
claude --version
```

## License

Internal Anthropic use.
