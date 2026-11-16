# Error-recovery sample files (for demonstrating Concept 6)

Upload these in the app to see safe, understandable error handling:

| File | Where to upload | Expected behaviour |
|---|---|---|
| `empty.log` | New Investigation -> log upload | Rejected: file is empty |
| `too_large.log` | New Investigation -> log upload | Rejected: larger than the 2 MB limit (Streamlit's uploader enforces the same limit, so you may see its message first) |
| `unsupported_type.csv` | Knowledge Base upload | Rejected: unsupported file type |
| `corrupt_report.pdf` | Knowledge Base upload | Recorded as **failed**, never as indexed |
| `invalid_yaml.yaml` | Kubernetes Analyzer | Parse error with line/column, no crash |

All files are synthetic.
