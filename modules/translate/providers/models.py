from typing import List, Dict, Any

TRANSLATION_PROVIDERS = [
    {
        "id": "gemini",
        "name": "Google Gemini",
        "env_var": "GEMINI_API_KEY",
        "secret_name": "gemini_api_key"
    }
]

# Bounded catalog specifying exactly three profile levels mapping to Gemini models with Vietnamese labels.
TRANSLATION_PROFILES = [
    {
        "id": "economy",
        "name": "Tiết kiệm (Gemini 3.5 Flash Lite)",
        "model": "gemini-3.5-flash-lite",
        "provider": "gemini",
        "description": "Dịch cực nhanh, tối ưu hóa chi phí cho các hội thoại cơ bản."
    },
    {
        "id": "balanced",
        "name": "Cân bằng (Gemini 3.5 Flash)",
        "model": "gemini-3.5-flash",
        "provider": "gemini",
        "description": "Khuyên dùng. Cân bằng tuyệt vời giữa tốc độ và hiểu bối cảnh."
    },
    {
        "id": "quality",
        "name": "Chất lượng cao (Gemini 3.6 Flash)",
        "model": "gemini-3.6-flash",
        "provider": "gemini",
        "description": "Xử lý văn học, ngôn từ ẩn dụ và xưng hô sâu sắc tốt nhất."
    }
]


def resolve_profile_to_model(profile_or_model: str) -> str:
    """
    Resolves a profile identifier (economy, balanced, quality) to its stable Gemini model ID.
    If the parameter is already a model ID, returns it directly.
    Raises ValueError for empty or unknown model profiles.
    """
    if not profile_or_model or not isinstance(profile_or_model, str) or not profile_or_model.strip():
        raise ValueError("Profile hoặc Model ID không được để trống.")

    p_clean = profile_or_model.strip()
    for p in TRANSLATION_PROFILES:
        if p["id"] == p_clean or p["model"] == p_clean:
            return p["model"]

    raise ValueError(f"Profile hoặc Model ID '{profile_or_model}' không hợp lệ.")


def resolve_profile_to_provider(profile_or_model: str) -> str:
    """
    Resolves a profile identifier or model ID to its provider ID.
    Defaults to 'gemini' if not specified or unknown.
    """
    if not profile_or_model or not isinstance(profile_or_model, str) or not profile_or_model.strip():
        return "gemini"

    p_clean = profile_or_model.strip()
    for p in TRANSLATION_PROFILES:
        if p["id"] == p_clean or p["model"] == p_clean:
            return p.get("provider", "gemini")

    return "gemini"
