package com.tabletopgame.storage;

import cn.nukkit.plugin.PluginBase;
import org.yaml.snakeyaml.DumperOptions;
import org.yaml.snakeyaml.Yaml;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Map;

/**
 * YAML 存档读写助手：四个棋类 Manager 共用。
 * <p>
 * {@link Yaml} 实例非线程安全，因此每次调用都新建一个（存档很小，开销可忽略）。
 * 运行期的 snakeyaml 由 Nukkit-MOT 内置提供（见 pom 中 okaeri-configs-yaml-snakeyaml 依赖注释）。
 */
public final class BoardStorage {

    private BoardStorage() {
    }

    /** 插件数据目录下的存档文件（目录不存在时创建）。 */
    public static File file(PluginBase plugin, String name) {
        File folder = plugin.getDataFolder();
        if (!folder.exists() && !folder.mkdirs()) {
            plugin.getLogger().warning("无法创建插件数据目录：" + folder.getPath());
        }
        return new File(folder, name);
    }

    /** 把数据结构序列化为 YAML 文本（块状风格，UTF-8 由调用方写盘时指定）。 */
    public static String dump(Object data) {
        DumperOptions options = new DumperOptions();
        options.setDefaultFlowStyle(DumperOptions.FlowStyle.BLOCK);
        options.setIndent(2);
        options.setPrettyFlow(true);
        return new Yaml(options).dump(data);
    }

    /** 读取 YAML 文件；文件不存在或解析失败返回 null。 */
    public static Object load(File file) {
        if (!file.isFile()) {
            return null;
        }
        try {
            return new Yaml().load(Files.readString(file.toPath(), StandardCharsets.UTF_8));
        } catch (IOException | RuntimeException e) {
            return null;
        }
    }

    /** 从 YAML 映射读字符串，缺失或类型不符返回默认值。 */
    public static String stringValue(Map<?, ?> map, String key, String fallback) {
        Object value = map.get(key);
        return value == null ? fallback : String.valueOf(value);
    }

    /** 从 YAML 映射读整数（Number 与数字字符串均可），缺失或无法解析返回默认值。 */
    public static int intValue(Map<?, ?> map, String key, int fallback) {
        Object value = map.get(key);
        if (value instanceof Number number) {
            return number.intValue();
        }
        try {
            return Integer.parseInt(String.valueOf(value));
        } catch (NumberFormatException e) {
            return fallback;
        }
    }

    /** 从 YAML 映射读小数（Number 与数字字符串均可），缺失或无法解析返回默认值。 */
    public static double doubleValue(Map<?, ?> map, String key, double fallback) {
        Object value = map.get(key);
        if (value instanceof Number number) {
            return number.doubleValue();
        }
        try {
            return Double.parseDouble(String.valueOf(value));
        } catch (NumberFormatException e) {
            return fallback;
        }
    }

    /** 从 YAML 映射读布尔（仅接受 Boolean），缺失返回默认值。 */
    public static boolean boolValue(Map<?, ?> map, String key, boolean fallback) {
        Object value = map.get(key);
        return value instanceof Boolean flag ? flag : fallback;
    }
}
