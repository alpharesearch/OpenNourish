# This script will output a snapshot of the project to project_snapshot.txt

# Start with a clean file and a header
echo "Project Snapshot for OpenNourish" > project_snapshot.txt
echo "Generated on: $(date)" >> project_snapshot.txt
echo "========================================\n" >> project_snapshot.txt

# Find all relevant files, excluding ignored/binary directories and files
find . -type f \
    -not -path "./usda_data/*" \
    -not -path "./.git/*" \
    -not -path "./__pycache__/*" \
    -not -path "./migrations/*" \
    -not -path "./.pytest_cache/*" \
    -not -path "./typst/*" \
    -not -path "./certs/*" \
    -not -path "./.vscode/*" \
    -not -path "./persistent/*" \
    -not -path "./static/*" \
    -not -name "*.db" \
    -not -name "*.db-journal" \
    -not -name "*.pyc" \
    -not -name "*.ico" \
    -not -name "*.env" \
    -not -name "*.js" \
    -not -name "requirements.txt" \
    | while read -r file; do
        # For each file, print a clear header and then the file's content
        echo "--- FILE: ${file} ---" >> project_snapshot.txt
        cat "${file}" >> project_snapshot.txt
        echo -e "\n\n" >> project_snapshot.txt
    done

echo "Snapshot created successfully in project_snapshot.txt"
