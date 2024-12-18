try:
    import git
    HAS_GIT = True
except ImportError:
    HAS_GIT = False
import os
import re
import argparse
import shutil
import sys
from urllib.parse import urlparse
from pathlib import Path
import tempfile
import datetime
from typing import Optional, Union
import ell
import subprocess
from colorama import init, Fore, Style
import emoji
from typing import Dict, List
import time

# Initialize colorama
init()

class Stats:
    """Track repository statistics."""
    
    def __init__(self):
        self.total_files = 0
        self.total_size = 0
        self.binary_files = 0
        self.text_files = 0
        self.start_time = time.time()
    
    def add_file(self, file_path: str, size: int, is_binary: bool):
        """Add file statistics."""
        self.total_files += 1
        self.total_size += size
        if is_binary:
            self.binary_files += 1
        else:
            self.text_files += 1
    
    def print_summary(self):
        """Print statistics summary."""
        elapsed_time = time.time() - self.start_time
        
        print(f"\n{emoji.emojize(':bar_chart:')} {Fore.CYAN}Repository Statistics:{Style.RESET_ALL}")
        print(f"{Fore.BLUE}•{Style.RESET_ALL} Total files: {self.total_files}")
        print(f"{Fore.BLUE}•{Style.RESET_ALL} Text files: {self.text_files}")
        print(f"{Fore.BLUE}•{Style.RESET_ALL} Binary files: {self.binary_files}")
        print(f"{Fore.BLUE}•{Style.RESET_ALL} Total size: {self._format_size(self.total_size)}")
        print(f"{Fore.BLUE}•{Style.RESET_ALL} Processing time: {elapsed_time:.2f} seconds")
    
    @staticmethod
    def _format_size(size: int) -> str:
        """Format size in bytes to human readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

class Git2Markdown:
    def __init__(self, source: Union[str, Path], auth_token=None, ssh_key=None, output_dir=None):
        """Initialize Git2Markdown converter.
        
        Args:
            source: Git repository URL or local path
            auth_token: Optional personal access token
            ssh_key: Optional path to SSH key
            output_dir: Optional output directory
        """
        self.source = str(source)
        self.auth_token = auth_token
        self.ssh_key = ssh_key
        self.temp_dir = None
        self.is_local = os.path.exists(self.source)
        self.repo_name = self._get_repo_name()
        # Use repo name as output directory unless specified
        self.output_dir = output_dir or os.path.join(os.getcwd(), self.repo_name)
        self.stats = Stats()  # Add stats object

    def _get_repo_name(self):
        """Extract and format repository/folder name."""
        if self.is_local:
            name = os.path.basename(os.path.abspath(self.source))
        else:
            parsed = urlparse(self.source)
            path = parsed.path.strip('/')
            # Handle organization/repo format
            if '/' in path:
                org, repo = path.split('/')[:2]
                name = f"{org}-{repo}"
            else:
                name = path
            name = name.replace('.git', '')
        
        # Clean up the name
        return name.replace('/', '-').replace('_', '-').lower()

    def _clone_with_gh(self, clone_url, destination):
        """Clone repository using gh CLI."""
        try:
            # If GITHUB_TOKEN is set, use it directly for cloning but securely
            if os.getenv('GITHUB_TOKEN'):
                # Extract owner and repo from URL
                parsed = urlparse(clone_url)
                path_parts = parsed.path.strip('/').split('/')
                if len(path_parts) >= 2:
                    owner, repo = path_parts[:2]
                    repo = repo.replace('.git', '')
                    
                    # Use git config to set credentials without exposing in URL
                    if HAS_GIT:
                        # Use GitPython with credentials
                        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                            f.write(f"https://{os.getenv('GITHUB_TOKEN')}:x-oauth-basic@github.com")
                        try:
                            os.environ['GIT_ASKPASS'] = 'echo'  # Prevent password prompt
                            os.environ['GIT_TERMINAL_PROMPT'] = '0'
                            git.Repo.clone_from(f"https://github.com/{owner}/{repo}.git", 
                                              destination,
                                              env={'GIT_CONFIG_PARAMETERS': 
                                                   f"'credential.helper=store --file={f.name}'"})
                        finally:
                            os.unlink(f.name)
                    else:
                        # Use git CLI with credentials
                        subprocess.run(['git', 'config', '--global', 'credential.helper', 'store'])
                        subprocess.run(['git', 'clone', f"https://github.com/{owner}/{repo}.git", 
                                     destination],
                                     env={'GIT_ASKPASS': 'echo',
                                         'GIT_TERMINAL_PROMPT': '0',
                                         'GITHUB_TOKEN': os.getenv('GITHUB_TOKEN')},
                                     check=True, capture_output=True, text=True)
                    return True
                return False

            # Otherwise try gh CLI authentication
            auth_status = subprocess.run(['gh', 'auth', 'status'], 
                                      capture_output=True, text=True)
            if auth_status.returncode != 0:
                print("GitHub CLI is not authenticated. Please run:")
                print("gh auth login")
                return False

            subprocess.run(['gh', 'repo', 'clone', clone_url, destination], 
                         check=True, capture_output=True, text=True)
            return True
        except subprocess.CalledProcessError as e:
            if "auth" in str(e.stderr):
                print("GitHub CLI authentication required. Please run:")
                print("gh auth login")
            else:
                print(f"Error cloning with gh: {e.stderr}")
            return False
        except FileNotFoundError:
            print("Neither GitPython nor git CLI found. Please install one of them:")
            print("pip install gitpython")
            print("or")
            print("git --version  # to check if git is installed")
            return False
        except Exception as e:
            print(f"Unexpected error while cloning: {e}")
            return False

    def _prepare_source(self):
        """Prepare repository source directory."""
        if self.is_local:
            return self.source
            
        self.temp_dir = tempfile.mkdtemp()
        clone_url = self._prepare_clone_url()
        
        # Configure git with SSH key if provided
        if self.ssh_key and HAS_GIT:
            git_ssh_cmd = f'ssh -i {self.ssh_key}'
            os.environ['GIT_SSH_COMMAND'] = git_ssh_cmd

        try:
            if HAS_GIT:
                git.Repo.clone_from(clone_url, self.temp_dir)
            else:
                if not self._clone_with_gh(clone_url, self.temp_dir):
                    return None
            return self.temp_dir
        except Exception as e:
            print(f"Error cloning repository: {e}")
            if "Authentication failed" in str(e):
                print("Authentication failed. Please check your credentials.")
            return None

    def _prepare_clone_url(self):
        """Prepare repository URL with authentication if needed."""
        if self.auth_token:
            parsed = urlparse(self.source)
            return f"https://{self.auth_token}@{parsed.netloc}{parsed.path}"
        return self.source

    def analyze_repo_structure(self, source_dir):
        """Analyze repository structure."""
        print(f"\n{emoji.emojize(':magnifying_glass_tilted_right:')} {Fore.CYAN}Analyzing repository structure...{Style.RESET_ALL}")
        
        structure = {}
        
        # List of files/directories to ignore with proper regex patterns
        ignore_patterns = [
            r'\.git',
            r'__pycache__',
            r'.*\.pyc$',
            r'\.DS_Store'
        ]
        
        # Compile regex patterns
        ignore_regex = [re.compile(pattern) for pattern in ignore_patterns]
        
        for root, dirs, files in os.walk(source_dir):
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if not any(
                pattern.match(d) for pattern in ignore_regex
            )]
            
            current_level = structure
            relative_path = os.path.relpath(root, source_dir)

            if relative_path == ".":
                path_parts = []
            else:
                path_parts = relative_path.split(os.sep)

            for part in path_parts:
                if part not in current_level:
                    current_level[part] = {}
                current_level = current_level[part]

            for file in files:
                # Skip ignored files
                if any(pattern.match(file) for pattern in ignore_regex):
                    continue
                    
                try:
                    file_path = os.path.join(root, file)
                    file_size = os.path.getsize(file_path)
                    is_binary = self._is_binary_file(file_path)
                    
                    self.stats.add_file(file_path, file_size, is_binary)
                    
                    if is_binary:
                        current_level[file] = "[Binary file]"
                    else:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            current_level[file] = f.read()
                        
                    print(f"{Fore.GREEN}•{Style.RESET_ALL} Processing: {file_path}")
                        
                except Exception as e:
                    current_level[file] = f"[Error reading file: {str(e)}]"
                    print(f"{Fore.RED}✗{Style.RESET_ALL} Error processing: {file_path}")

        return structure

    @staticmethod
    def _is_binary_file(file_path):
        """Check if a file is binary."""
        try:
            with open(file_path, 'tr') as f:
                f.read(1024)
                return False
        except UnicodeDecodeError:
            return True

    def generate_markdown(self, repo_structure):
        """Generate Markdown content."""
        markdown_content = f"# {self.repo_name}\n\n"

        def _generate_markdown_recursive(structure, level):
            for name, content in sorted(structure.items()):
                if isinstance(content, dict):
                    markdown_content = f"{'#' * (level + 2)} {name}\n\n"
                    yield markdown_content
                    yield from _generate_markdown_recursive(content, level + 1)
                else:
                    yield f"{'#' * (level + 3)} {name}\n\n"
                    yield f"```\n{content}\n```\n\n"

        return "".join(_generate_markdown_recursive(repo_structure, 0))

    def generate_mermaid_diagram(self, repo_structure):
        """Generate Mermaid diagram."""
        mermaid_content = ["graph TD"]
        mermaid_content.append(f"    A[{self.repo_name}]")
        node_counter = 1

        def _generate_mermaid_recursive(structure, parent_node):
            nonlocal node_counter
            for name, content in sorted(structure.items()):
                current_node = f"N{node_counter}"
                node_counter += 1
                if isinstance(content, dict):
                    mermaid_content.append(
                        f"    {parent_node} --> {current_node}[{name}]"
                    )
                    _generate_mermaid_recursive(content, current_node)
                else:
                    mermaid_content.append(
                        f"    {parent_node} --> {current_node}{{'{name}'}}"
                    )

        _generate_mermaid_recursive(repo_structure, "A")
        return "\n".join(mermaid_content)

    def cleanup(self):
        """Clean up temporary files."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    @ell.simple(model="claude-3-5-sonnet-20241022", max_tokens=8192)
    def generate_llms_txt(self, repo_structure):
        """Generate a llms.txt file following the format from https://llmstxt.org/:
        Focus on providing clear, structured information for LLMs.
~~~
# {{ repo_name }}

## Repository Overview
{% if repo_description %}
{{ repo_description }}
{% endif %}

## Key Statistics
{% for stat, value in repo_stats.items() %}
- {{ stat }}: {{ value }}
{% endfor %}

## Important Files
{% for file in important_files %}
### {{ file.name }}
{{ file.description }}
{% endfor %}

## Key Components
{% for component in key_components %}
### {{ component.name }}
{{ component.purpose }}
{% endfor %}

## Dependencies
{% for dep in dependencies %}
- {{ dep.name }} ({{ dep.version }}){% if dep.purpose %}: {{ dep.purpose }}{% endif %}
{% endfor %}

## Documentation
{% for doc in documentation_files %}
### {{ doc.name }}
{{ doc.summary }}
{% endfor %}

## Code Examples
{% for example in code_examples %}
### {{ example.name }}
```{{ example.language }}
{{ example.code }}
```
{% endfor %}

## Additional Context
{% if additional_context %}
{{ additional_context }}
{% endif %}

## Repository Statistics
- Total Files: {{ repo_stats.total_files }}
- Lines of Code: {{ repo_stats.total_lines }}
- Repository Size: {{ repo_stats.total_size_mb }}MB
- File Types: {{ repo_stats.file_types | join(', ') }} 
~~~
        No "Here's a formatted llms.txt" or similar, just the content.
        """
        files = []
        readme_content = None
        main_file = None
        test_files = []
        config_files = []
        
        def collect_files(structure, path=""):
            nonlocal readme_content, main_file
            for name, content in structure.items():
                full_path = f"{path}/{name}" if path else name
                if isinstance(content, dict):
                    collect_files(content, full_path)
                else:
                    files.append((full_path, content))
                    if name.lower() == "readme.md":
                        readme_content = content
                    elif name.lower() in ["main.py", "index.js", "app.py"]:
                        main_file = (full_path, content)
                    elif "test" in name.lower():
                        test_files.append((full_path, content))
                    elif name.lower() in ["config.json", "settings.py", ".env.example"]:
                        config_files.append((full_path, content))
        
        collect_files(repo_structure)
        
        # Build llms.txt content
        sections = []
        
        # Project Overview
        sections.append(f"# {self.repo_name}")
        if readme_content:
            overview = readme_content.split("\n\n")[0]  # First paragraph
            sections.append(overview)
        sections.append("")
        
        # Technical Stack
        sections.append("## Technical Stack")
        tech_stack = self._detect_tech_stack(files)
        sections.extend([f"- {tech}" for tech in tech_stack])
        sections.append("")
        
        # Core Functionality
        sections.append("## Core Functionality")
        if main_file:
            sections.append(f"Main entry point: {main_file[0]}")
            sections.append("Key operations:")
            sections.extend(self._extract_key_functions(main_file[1]))
        sections.append("")
        
        # Configuration
        if config_files:
            sections.append("## Configuration")
            sections.append("Required configuration:")
            for config_file, content in config_files:
                sections.append(f"### {config_file}")
                sections.append(self._extract_config_details(content))
            sections.append("")
        
        # Error Handling
        sections.append("## Error Handling")
        error_patterns = self._extract_error_patterns(files)
        sections.extend(error_patterns)
        sections.append("")
        
        # Usage Examples
        sections.append("## Usage Examples")
        examples = self._extract_examples(files)
        sections.extend(examples)
        sections.append("")
        
        # Development Notes
        if test_files:
            sections.append("## Development Notes")
            sections.append("Testing approach:")
            sections.extend(self._extract_test_patterns(test_files))
        
        return "\n".join(sections)

    def _detect_tech_stack(self, files):
        """Detect technical stack based on file extensions and content."""
        tech_stack = set()
        for path, content in files:
            if path.endswith(".py"):
                tech_stack.add("Python")
            elif path.endswith(".js"):
                tech_stack.add("JavaScript")
            elif path.endswith(".tsx"):
                tech_stack.add("TypeScript/React")
            # Add more technology detection patterns
        return sorted(list(tech_stack))

    def _extract_key_functions(self, content):
        """Extract and document key functions from the main file."""
        functions = []
        import ast
        try:
            # Parse Python code
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    doc = ast.get_docstring(node) or "No description available"
                    args = [arg.arg for arg in node.args.args]
                    first_doc_line = doc.split('\n')[0] if '\n' in doc else doc
                    functions.append(f"- `{node.name}({', '.join(args)})`: {first_doc_line}")
        except:
            # Fallback for non-Python files
            import re
            # Match function definitions in various languages
            patterns = [
                r'function\s+(\w+)\s*\((.*?)\)\s*{',  # JavaScript
                r'def\s+(\w+)\s*\((.*?)\):',          # Python
                r'pub\s+fn\s+(\w+)\s*\((.*?)\)',      # Rust
            ]
            for pattern in patterns:
                matches = re.finditer(pattern, content)
                for match in matches:
                    name, args = match.groups()
                    functions.append(f"- `{name}({args})`: Function definition")
        
        return functions if functions else ["No functions extracted"]

    def _extract_config_details(self, content):
        """Extract and format configuration requirements."""
        details = []
        import re
        
        # Look for environment variables
        env_pattern = r'([A-Z_]+)\s*=\s*[\'"]?([^\'"]*)[\'"]?'
        env_vars = re.finditer(env_pattern, content)
        for match in env_vars:
            var_name, default_value = match.groups()
            details.append(f"- `{var_name}`: Required environment variable" + 
                          (f" (default: {default_value})" if default_value else ""))
        
        # Look for configuration objects
        config_patterns = [
            r'config\s*=\s*{([^}]*)}',
            r'settings\s*=\s*{([^}]*)}',
        ]
        for pattern in config_patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                config_block = match.group(1)
                for line in config_block.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        details.append(f"- `{key.strip()}`: {value.strip()}")
        
        return details if details else ["No configuration details found"]

    def _extract_error_patterns(self, files):
        """Document error handling patterns."""
        patterns = []
        import re
        
        error_patterns = set()
        for path, content in files:
            # Look for custom exceptions
            custom_exceptions = re.finditer(
                r'class\s+(\w+Error)\s*\(\w+\)', 
                content
            )
            for match in custom_exceptions:
                error_patterns.add(f"- Custom exception: `{match.group(1)}`")
            
            # Look for try/except blocks
            try_blocks = re.finditer(
                r'try:.*?except\s+(\w+(?:\s*,\s*\w+)*)\s*as\s+\w+:', 
                content, 
                re.DOTALL
            )
            for match in try_blocks:
                exceptions = match.group(1).split(',')
                for exc in exceptions:
                    error_patterns.add(f"- Handles: `{exc.strip()}`")
        
        patterns.extend(sorted(error_patterns))
        return patterns if patterns else ["No error handling patterns documented"]

    def _extract_examples(self, files):
        """Extract usage examples from documentation and code."""
        examples = []
        
        # Look for example code in docstrings and comments
        for path, content in files:
            import re
            
            # Extract code blocks from markdown files
            if path.lower().endswith(('.md', '.rst')):
                code_blocks = re.finditer(
                    r'```(?:\w+)?\n(.*?)\n```',
                    content,
                    re.DOTALL
                )
                for block in code_blocks:
                    code = block.group(1).strip()
                    if len(code.split('\n')) < 15:  # Keep examples concise
                        examples.append("```\n" + code + "\n```")
            
            # Extract doctest examples from Python files
            if path.lower().endswith('.py'):
                doctests = re.finditer(
                    r'>>> (.*?)\n(?:\.{3,} .*?\n)*(?:[^>].*?\n)*',
                    content
                )
                for test in doctests:
                    examples.append(f"```python\n{test.group(0)}```")
        
        # Add example usage from README if available
        if any(f[0].lower() == 'readme.md' for f in files):
            readme = next(f[1] for f in files if f[0].lower() == 'readme.md')
            usage_section = re.search(
                r'#{1,2}\s*(?:Usage|Getting Started|Quick Start).*?\n(.*?)(?=\n#|\Z)',
                readme,
                re.DOTALL | re.IGNORECASE
            )
            if usage_section:
                examples.append(usage_section.group(1).strip())
        
        return examples if examples else ["No examples found"]

    def _extract_test_patterns(self, test_files):
        """Extract testing patterns and approaches."""
        patterns = []
        import re
        
        for path, content in test_files:
            # Extract test case names and descriptions
            test_cases = re.finditer(
                r'(?:def|test)\s+(test_\w+)',
                content
            )
            for test in test_cases:
                test_name = test.group(1)
                # Convert snake_case to readable description
                description = test_name.replace('test_', '').replace('_', ' ').capitalize()
                patterns.append(f"- {description}")
            
            # Look for testing frameworks
            frameworks = {
                'pytest': r'import\s+pytest',
                'unittest': r'import\s+unittest',
                'jest': r'describe\(',
                'mocha': r'describe\(',
            }
            for framework, pattern in frameworks.items():
                if re.search(pattern, content):
                    patterns.insert(0, f"Using {framework} testing framework")
                    break
        
        return patterns if patterns else ["No test patterns found"]

    def convert(self):
        """Convert repository to Markdown and Mermaid diagram."""
        try:
            print(f"\n{emoji.emojize(':rocket:')} {Fore.CYAN}Starting conversion...{Style.RESET_ALL}")
            
            source_dir = self._prepare_source()
            if not source_dir:
                print(f"{Fore.RED}✗ Failed to prepare source{Style.RESET_ALL}")
                return False

            repo_structure = self.analyze_repo_structure(source_dir)

            print(f"\n{emoji.emojize(':writing_hand:')} {Fore.CYAN}Generating documentation...{Style.RESET_ALL}")
            
            os.makedirs(self.output_dir, exist_ok=True)

            # Generate files with progress indicators
            files_to_generate = [
                ("README.md", self.generate_markdown),
                ("structure.mmd", self.generate_mermaid_diagram),
                ("llms.txt", self.generate_llms_txt)
            ]

            for filename, generator in files_to_generate:
                output_path = os.path.join(self.output_dir, filename)
                print(f"{Fore.GREEN}•{Style.RESET_ALL} Generating {filename}...")
                
                content = generator(repo_structure)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(content)

            self.stats.print_summary()

            print(f"\n{emoji.emojize(':check_mark_button:')} {Fore.GREEN}Files generated successfully in {self.output_dir}:{Style.RESET_ALL}")
            for filename, _ in files_to_generate:
                print(f"{Fore.BLUE}•{Style.RESET_ALL} {filename}")
            
            return True

        except Exception as e:
            print(f"\n{emoji.emojize(':cross_mark:')} {Fore.RED}Error during conversion: {e}{Style.RESET_ALL}")
            return False
        finally:
            self.cleanup()

def main():
    parser = argparse.ArgumentParser(description="Convert Git repository or local folder to Markdown documentation")
    parser.add_argument("source", help="URL of the Git repository or path to local folder")
    parser.add_argument("--token", help="Personal access token for private repositories")
    parser.add_argument("--ssh-key", help="Path to SSH key for private repositories")
    parser.add_argument("--output-dir", help="Output directory for generated files")
    
    args = parser.parse_args()
    
    converter = Git2Markdown(
        args.source,
        auth_token=args.token,
        ssh_key=args.ssh_key,
        output_dir=args.output_dir
    )
    
    success = converter.convert()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()