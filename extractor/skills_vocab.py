"""
Shared skill vocabulary used by all parsers (resume, notes).
Kept in one place so the full set is consistent across sources.
Ordered roughly by domain for readability — matching is case-insensitive.
"""

KNOWN_SKILLS = [
    # Languages
    "python", "java", "javascript", "typescript", "c++", "cpp", "c#", "csharp",
    "go", "golang", "rust", "kotlin", "swift", "scala", "ruby", "php", "r",
    "matlab", "bash", "shell", "perl", "lua", "dart",

    # Web / Frontend
    "html", "css", "react", "next.js", "nextjs", "vue", "angular", "svelte",
    "tailwind", "bootstrap", "jquery", "redux", "graphql", "rest", "restful",

    # Backend / Frameworks
    "node", "node.js", "nodejs", "express", "express.js", "django", "flask",
    "fastapi", "spring", "spring boot", "laravel", "rails", "asp.net",

    # Databases
    "sql", "postgresql", "mysql", "sqlite", "mongodb", "firebase",
    "redis", "cassandra", "dynamodb", "neo4j", "elasticsearch",

    # Cloud / DevOps
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform", "ansible",
    "jenkins", "ci/cd", "linux", "nginx", "apache", "github actions",

    # ML / AI / Data Science
    "machine learning", "deep learning", "nlp", "computer vision",
    "tensorflow", "pytorch", "keras", "scikit-learn", "sklearn",
    "pandas", "numpy", "matplotlib", "seaborn", "xgboost", "lightgbm",
    "hugging face", "transformers", "langchain", "llm", "openai",
    "sentence transformers", "faiss", "chromadb", "pinecone", "qdrant",
    "rag", "vector database", "spacy", "nltk", "openCV", "opencv",

    # Data Engineering
    "spark", "hadoop", "kafka", "airflow", "dbt", "snowflake",
    "bigquery", "databricks",

    # Tools / Misc
    "git", "github", "gitlab", "jira", "figma", "postman",
    "jupyter", "colab", "streamlit", "gradio",
]
