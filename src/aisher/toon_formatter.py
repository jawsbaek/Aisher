from typing import List, Any
from pydantic import BaseModel


class ToonFormatter:
    """
    TOON (Token-Oriented Object Notation) Implementation.
    Optimizes tabular data for LLM token efficiency.
    Ref: https://github.com/toon-format/spec
    """

    @staticmethod
    def _escape_string(value: Any, delimiter: str) -> str:
        """
        TOON string escaping rules:
        1. Newlines → \\n (preserve table structure)
        2. Quotes → \\"
        3. Quote if contains delimiter or leading/trailing spaces
        """
        if value is None:
            return "null"

        val_str = str(value)

        # Escape special characters
        val_str = (val_str
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )

        # Quote if necessary
        needs_quotes = (
            delimiter in val_str or
            val_str.startswith(" ") or
            val_str.endswith(" ") or
            val_str == "" or
            any(c in val_str for c in "{}:[]")  # Structural characters
        )

        return f'"{val_str}"' if needs_quotes else val_str

    @classmethod
    def format_tabular(cls, data: List[BaseModel], array_name: str = "errors") -> str:
        """
        Convert Pydantic model list to TOON Tabular Array format.
        Example: errors[5]{id,svc,msg}:\nabc,api,Error\n...
        """
        if not data:
            return f"{array_name}[0]:"

        # 1. Extract dictionaries
        dicts = [item.model_dump() for item in data]
        if not dicts:
            return f"{array_name}[0]:"

        headers = list(dicts[0].keys())  # FIX: Use first dict's keys

        # 2. Cost-based delimiter optimization
        sample_text = " ".join([str(v) for row in dicts for v in row.values()])
        comma_count = sample_text.count(',')
        pipe_count = sample_text.count('|')

        delimiter = '|' if comma_count > pipe_count * 2 else ','

        # 3. Build header: array_name[count|]{col1,col2}:
        count = len(data)
        delim_marker = '|' if delimiter == '|' else ''  # Comma is default
        header_line = f"{array_name}[{count}{delim_marker}]{{{','.join(headers)}}}:"

        # 4. Build rows
        lines = [header_line]
        for row in dicts:
            values = [cls._escape_string(row[k], delimiter) for k in headers]
            lines.append(delimiter.join(values))

        return "\n".join(lines)
