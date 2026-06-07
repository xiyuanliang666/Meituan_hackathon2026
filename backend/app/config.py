from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    model_real_enabled: bool = Field(default=True, alias="MODEL_REAL_ENABLED")
    model_timeout_seconds: float = Field(default=30.0, alias="MODEL_TIMEOUT_SECONDS")

    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai",
        alias="GEMINI_BASE_URL",
    )
    gemini_model_name: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL_NAME")

    qwen_api_key: str | None = Field(default=None, alias="QWEN_API_KEY")
    qwen_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        alias="QWEN_BASE_URL",
    )
    qwen_vl_model_name: str = Field(default="qwen-vl-plus", alias="QWEN_VL_MODEL_NAME")

    nail_region_vlm_api_key: str | None = Field(default=None, alias="NAIL_REGION_VLM_API_KEY")
    nail_region_vlm_base_url: str = Field(
        default="https://api.openai.com/v1",
        alias="NAIL_REGION_VLM_BASE_URL",
    )
    nail_region_vlm_model_name: str = Field(default="gpt-5.5", alias="NAIL_REGION_VLM_MODEL_NAME")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    image_model_name: str = Field(default="gpt-image-1", alias="IMAGE_MODEL_NAME")
    image_generation_enabled: bool = Field(default=False, alias="IMAGE_GENERATION_ENABLED")
    storage_dir: str = Field(default="./storage", alias="STORAGE_DIR")
    public_base_url: str = Field(default="http://127.0.0.1:8000/static", alias="PUBLIC_BASE_URL")
    eval_dataset_path: str = Field(
        default="../运营侧/命题三美甲评测数据（对外版）.xlsx",
        alias="EVAL_DATASET_PATH",
    )
    database_path: str = Field(default="./storage/nail_ai_demo.db", alias="DATABASE_PATH")

    @property
    def has_gemini_credentials(self) -> bool:
        return bool(self.model_real_enabled and self.gemini_api_key)

    @property
    def has_qwen_credentials(self) -> bool:
        return bool(self.model_real_enabled and self.qwen_api_key)

    @property
    def has_nail_region_vlm_credentials(self) -> bool:
        return bool(self.model_real_enabled and self.nail_region_vlm_api_key)

    @property
    def has_image_generation_credentials(self) -> bool:
        return bool(self.image_generation_enabled and self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
