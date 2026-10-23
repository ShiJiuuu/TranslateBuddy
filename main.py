from dify_plugin import DifyPluginEnv, Plugin

# 单次调用最长 1800s：与 plugin_daemon 的 PLUGIN_MAX_EXECUTION_TIMEOUT 对齐
plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=1800))

if __name__ == "__main__":
    plugin.run()
