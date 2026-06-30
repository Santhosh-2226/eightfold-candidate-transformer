"""
Canonicalization: collapse semantically-equivalent values to one
canonical form. This is distinct from formatting normalization
(E.164, YYYY-MM) -- it's about recognizing "Google Inc." and "Google"
are the same entity, or "CPP" and "C++" are the same skill.

Deliberately a static dictionary, not ML-based -- keeps this
fully deterministic and explainable.
"""
import re

# ──────────────────────────────────────────────────────────────────────────
# Skill aliases: lowercased-key -> canonical display form.
# Anything NOT in this dict falls back to .title(), which is why things
# like "Pytorch" / "Fastapi" / "Faiss" were showing up wrong before --
# they simply weren't in the dictionary, so .title() ran on them as
# regular words. Every skill the resume vocab can emit should have an
# explicit entry here so casing is never left to chance.
# ──────────────────────────────────────────────────────────────────────────
SKILL_ALIASES = {
    # languages
    "cpp": "C++", "c++": "C++",
    "c#": "C#", "csharp": "C#",
    "js": "JavaScript", "javascript": "JavaScript",
    "ts": "TypeScript", "typescript": "TypeScript",
    "java": "Java",
    "sql": "SQL",
    "html": "HTML", "css": "CSS",
    "golang": "Go", "go": "Go",
    "php": "PHP",
    "bash": "Bash", "shell": "Shell",

    # ML / data
    "ml": "Machine Learning", "machine learning": "Machine Learning",
    "deep learning": "Deep Learning",
    "nlp": "NLP",
    "llm": "LLM", "llms": "LLM",
    "rag": "RAG",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "scikit-learn": "scikit-learn", "sklearn": "scikit-learn",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "nltk": "NLTK",
    "spacy": "spaCy",
    "opencv": "OpenCV",
    "numpy": "NumPy",
    "pandas": "Pandas",
    "matplotlib": "Matplotlib",
    "seaborn": "Seaborn",
    "transformers": "Transformers",
    "hugging face": "Hugging Face", "huggingface": "Hugging Face",
    "sentence transformers": "Sentence Transformers",
    "openai": "OpenAI",
    "langchain": "LangChain",
    "faiss": "FAISS",
    "chromadb": "ChromaDB", "chroma": "ChromaDB",
    "pinecone": "Pinecone",
    "qdrant": "Qdrant",
    "neo4j": "Neo4j",
    "computer vision": "Computer Vision",
    "vector database": "Vector Database",

    # web / API
    "rest": "REST", "restful": "RESTful",
    "graphql": "GraphQL",
    "tailwind": "Tailwind CSS",
    "bootstrap": "Bootstrap",
    "jquery": "jQuery",
    "redux": "Redux",

    # backend / web frameworks
    "node": "Node.js", "node.js": "Node.js", "nodejs": "Node.js",
    "express": "Express.js", "express.js": "Express.js", "expressjs": "Express.js",
    "next.js": "Next.js", "nextjs": "Next.js",
    "react": "React", "react.js": "React",
    "vue": "Vue.js", "vue.js": "Vue.js",
    "angular": "Angular",
    "svelte": "Svelte",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "django": "Django",
    "spring": "Spring", "spring boot": "Spring Boot",
    "asp.net": "ASP.NET",
    "rails": "Rails",
    "laravel": "Laravel",

    # databases
    "mongodb": "MongoDB", "mongo": "MongoDB",
    "postgresql": "PostgreSQL", "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "sqlite": "SQLite",
    "firebase": "Firebase",
    "redis": "Redis",
    "cassandra": "Cassandra",
    "dynamodb": "DynamoDB",
    "elasticsearch": "Elasticsearch",
    "bigquery": "BigQuery",
    "snowflake": "Snowflake",
    "databricks": "Databricks",

    # devops / cloud / tools
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "git": "Git",
    "github": "GitHub",
    "gitlab": "GitLab",
    "jenkins": "Jenkins",
    "linux": "Linux",
    "aws": "AWS",
    "gcp": "GCP",
    "azure": "Azure",
    "terraform": "Terraform",
    "ansible": "Ansible",
    "ci/cd": "CI/CD",
    "github actions": "GitHub Actions",
    "nginx": "Nginx",
    "apache": "Apache",
    "postman": "Postman",
    "figma": "Figma",
    "streamlit": "Streamlit",
    "gradio": "Gradio",
    "jupyter": "Jupyter",
    "colab": "Google Colab",
    "jira": "Jira",

    # data engineering
    "spark": "Apache Spark",
    "hadoop": "Hadoop",
    "kafka": "Apache Kafka",
    "airflow": "Apache Airflow",
    "dbt": "dbt",
}

COMPANY_SUFFIX_RE = re.compile(
    r"\s*[,]?\s*\b(inc\.?|llc\.?|corp\.?|corporation|limited)\b\.?\s*$",
    re.IGNORECASE,
)
# "Pvt" / "Ltd" are kept (common in Indian company names like "X Pvt Ltd")
# rather than stripped -- only fixed-case via _COMPANY_WORD_FIXUPS below.

# Known acronyms / words that should stay uppercase (or a fixed case)
# rather than be title-cased, when they appear as standalone words in
# a company/institution name (e.g. "Cit Chennai" -> "CIT Chennai").
_COMPANY_WORD_FIXUPS = {
    "cit": "CIT", "iit": "IIT", "nit": "NIT", "bits": "BITS",
    "llc": "LLC", "inc": "Inc.", "pvt": "Pvt", "ltd": "Ltd",
    "llp": "LLP", "ai": "AI", "it": "IT",
}

_SMALL_WORDS = {"of", "and", "the", "for", "in", "at", "&"}


def canonicalize_skill(name: str) -> str:
    if not name:
        return name
    key = name.strip().lower()
    return SKILL_ALIASES.get(key, name.strip().title())


def canonicalize_company(name: str) -> str:
    """
    Strip legal suffixes, then word-by-word title-case while fixing
    known acronyms (CIT, IIT, AI, ...) and known suffix words (Pvt, Ltd)
    that .title() alone gets wrong (e.g. "cit chennai research center"
    -> "CIT Chennai Research Center", not "Cit Chennai Research Center"),
    and keeping small connective words ("of", "and") lowercase mid-string.
    """
    if not name:
        return name
    cleaned = COMPANY_SUFFIX_RE.sub("", name.strip())
    cleaned = cleaned.strip() or name.strip()

    words = cleaned.split()
    fixed_words = []
    for idx, w in enumerate(words):
        bare = re.sub(r"[^A-Za-z]", "", w).lower()
        if bare in _COMPANY_WORD_FIXUPS:
            suffix = w[len(re.sub(r"[^A-Za-z]", "", w)):] if bare else ""
            fixed_words.append(_COMPANY_WORD_FIXUPS[bare] + suffix)
        elif bare in _SMALL_WORDS and idx != 0:
            fixed_words.append(w.lower())
        else:
            fixed_words.append(w[:1].upper() + w[1:] if w else w)
    return " ".join(fixed_words)


DEGREE_ALIASES = {
    "master of science": "MS",
    "m.s.": "MS",
    "ms": "MS",
    "bachelor of technology": "B.Tech",
    "b.tech": "B.Tech",
    "btech": "B.Tech",
    "bachelor of science": "BS",
    "bs": "BS",
    "be": "B.E.",
    "b.e": "B.E.",
}


def canonicalize_degree(name: str) -> str:
    if not name:
        return name
    key = name.strip().lower()
    return DEGREE_ALIASES.get(key, name.strip())


# Markers that indicate a string is an educational institution, not an
# employer -- used to keep things like "Chennai Institute of Technology"
# out of current_company, regardless of which source claimed it.
_EDU_MARKERS_RE = re.compile(
    r"\b(university|institute of technology|college|polytechnic|school of|"
    r"b\.?tech|m\.?tech|cgpa|gpa\b|b\.?sc|m\.?sc|bachelor|master)\b",
    re.IGNORECASE,
)


def looks_like_education_institution(name: str) -> bool:
    """True if `name` reads like a school/university rather than an employer."""
    if not name:
        return False
    return bool(_EDU_MARKERS_RE.search(name))