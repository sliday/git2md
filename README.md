# git2md

Convert Git repositories or local folders into structured documentation, including llms.txt format for LLM context.

## Features

- Generates structured Markdown documentation from repositories
- Creates Mermaid diagrams of repository structure
- Produces llms.txt following [llmstxt.org](https://llmstxt.org) format
- Supports both remote Git repositories and local folders
- Handles authentication for private repositories
- Provides detailed repository statistics

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/git2md.git
cd git2md

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
# Convert a public GitHub repository
python git2md.py https://github.com/username/repo

# Convert a local folder
python git2md.py /path/to/folder
```

### Authentication Options

```bash
# Using a personal access token
python git2md.py https://github.com/username/private-repo --token YOUR_TOKEN

# Using SSH key
python git2md.py git@github.com:username/private-repo.git --ssh-key ~/.ssh/id_rsa
```

### Custom Output Directory

```bash
# Specify output directory
python git2md.py https://github.com/username/repo --output-dir ./docs
```

## Output Files

The tool generates three files in the output directory:

1. `README.md` - Comprehensive Markdown documentation
2. `structure.mmd` - Mermaid diagram of repository structure
3. `llms.txt` - LLM-optimized documentation following llmstxt.org format

## Requirements

- Python 3.7+
- GitPython (optional, for enhanced Git support)
- GitHub CLI (optional, for authentication)

## Environment Variables

- `GITHUB_TOKEN` - GitHub personal access token (optional)
- `GIT_SSH_COMMAND` - Custom SSH command (optional)

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.