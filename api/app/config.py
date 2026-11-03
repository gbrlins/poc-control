from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "db"
    postgres_port: int = 5432

    admin_email: str
    admin_password_hash: str

    session_secret: str
    session_max_age_seconds: int = 60 * 60 * 24 * 7

    gemini_api_key: str = ""

    uploads_dir: str = "/app/uploads"

    # ADR 7: na inicialização, marca como `erro` as extrações que ficaram em `extraindo` (a tarefa morreu com o processo).
    # Desligue se rodar a api com mais de um worker (senão um worker derruba tarefas vivas do outro).
    extracao_recuperar_no_inicio: bool = True

    # Sincronização de Procedimentos com outra instância do poc-control (ex.: local <-> servidor de
    # produção) -- ver app/sync/. Vazio por padrão: a funcionalidade fica escondida no front
    # (GET /api/sync/config) até os três estarem preenchidos. A senha nunca trafega pro navegador --
    # só este processo da api loga no servidor remoto.
    sync_servidor_url: str = ""
    sync_servidor_email: str = ""
    sync_servidor_senha: str = ""

    @property
    def sync_configurado(self) -> bool:
        return bool(self.sync_servidor_url and self.sync_servidor_email and self.sync_servidor_senha)

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
