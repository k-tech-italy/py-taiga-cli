"""Per-invocation state shared by commands (``ctx.obj``)."""

from __future__ import annotations

from dataclasses import dataclass, field

import click
import httpx

from taiga_cli import config, credentials, project_file
from taiga_cli.api.client import TaigaClient, Tokens, normalize_base_url
from taiga_cli.api.project_context import ProjectContext
from taiga_cli.errors import AuthError, ConfigError, UsageError
from taiga_cli.project_file import ProjectConfig

_UNSET = object()


@dataclass
class AppContext:
    profile_name: str | None = None
    # Injected by tests to mock HTTP; None means real network.
    transport: httpx.BaseTransport | None = None
    # False disables discovery of .taiga-cli-config.json (--no-project-config).
    use_project_config: bool = True
    _config: config.Config | None = field(default=None, repr=False)
    _project_config: object = field(default=_UNSET, repr=False)
    _client: TaigaClient | None = field(default=None, repr=False)

    @property
    def config(self) -> config.Config:
        if self._config is None:
            self._config = config.load()
        return self._config

    def project_config(self) -> ProjectConfig | None:
        """The repository's .taiga-cli-config.json, searched from the cwd upwards."""
        if self._project_config is _UNSET:
            self._project_config = project_file.discover() if self.use_project_config else None
        return self._project_config  # type: ignore[return-value]

    @property
    def resolved_profile_name(self) -> str:
        """-p NAME > profile referenced by the project config file > default profile."""
        if self.profile_name:
            return self.profile_name
        pc = self.project_config()
        if pc is not None and pc.profile:
            return pc.profile
        return self.config.default_profile

    def profile(self) -> config.Profile:
        profile = self.config.get_profile(self.resolved_profile_name)
        pc = self.project_config() if not self.profile_name else None
        if pc is not None and pc.profile == profile.name:
            self._check_same_instance(pc, profile)
        return profile

    def _check_same_instance(self, pc: ProjectConfig, profile: config.Profile) -> None:
        if normalize_base_url(profile.url) != normalize_base_url(pc.url):
            raise ConfigError(
                f"{pc.path} is for {pc.url} but profile '{profile.name}' is for {profile.url}; "
                f"run `taiga-cli -p NAME auth login --url {pc.url}` and set that profile name "
                "in the file, or pass -p"
            )

    def project_slug(self, explicit: str | None) -> str:
        """-P SLUG > project of the config file; error if neither is available."""
        if explicit:
            return explicit
        pc = self.project_config()
        if pc is None:
            raise UsageError(
                f"project required: use -P SLUG or SLUG#REF, or add a "
                f"{project_file.CONFIG_FILENAME} (`taiga-cli project configure export`)"
            )
        self._check_same_instance(pc, self.profile())
        return pc.slug

    def project_context(self, slug: str) -> ProjectContext:
        """Name resolver for a project; offline from the config file when it covers ``slug``."""
        client = self.client()
        pc = self.project_config()
        if (
            pc is not None
            and pc.slug == slug
            and normalize_base_url(pc.url) == normalize_base_url(self.profile().url)
        ):
            return ProjectContext.from_project_config(client, pc)
        return ProjectContext.load(client, slug)

    def new_client(self, url: str, tokens: Tokens | None = None) -> TaigaClient:
        name = self.resolved_profile_name

        def persist(new: Tokens) -> None:
            credentials.save_tokens(name, new)

        return TaigaClient(url, tokens, on_refresh=persist, transport=self.transport)

    def client(self) -> TaigaClient:
        """Authenticated client for the active profile."""
        if self._client is None:
            profile = self.profile()
            tokens = credentials.load_tokens(profile.name)
            if tokens is None:
                raise AuthError(
                    f"not logged in (profile '{profile.name}'); run `taiga-cli auth login`"
                )
            self._client = self.new_client(profile.url, tokens)
        return self._client

    def me_id(self) -> int:
        """Current user's id (cached in the profile at login; fetched otherwise)."""
        user_id = self.profile().user_id
        if user_id is None:
            user_id = int(self.client().get("/users/me")["id"])
        return user_id

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


pass_app = click.make_pass_decorator(AppContext)
