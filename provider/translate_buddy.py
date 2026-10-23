from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class TranslateBuddyProvider(ToolProvider):
    """本插件不需要平台凭证，翻译统一走 workspace 里已配置的模型。"""

    def _validate_credentials(self, credentials: dict) -> None:
        if not isinstance(credentials, dict):
            raise ToolProviderCredentialValidationError("credentials must be a dict")
