import eu.okaeri.configs.ConfigManager;
import eu.okaeri.configs.yaml.snakeyaml.YamlSnakeYamlConfigurer;
import com.tabletopgame.config.TabletopGameConfig;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * 配置生成/回读的离线验证：用与 TabletopGameManager.readConfig() 完全相同的配置器，
 * 把默认值写到临时文件（模拟首次启动），再回读一次（模拟第二次启动）。
 * 目的是确保 {@code @Comment} 的多行写法不会生成非法 YAML。
 */
public final class CfgCheck {

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("tg-cfgcheck");
        File file = dir.resolve("config.yml").toFile();

        // 第一次：文件不存在 -> saveDefaults + load
        TabletopGameConfig first = create(file);
        System.out.println("[1] 首次生成+回读  OK   minStartBalance="
                + first.getGambling().getMinStartBalance());
        System.out.println("[1] 文件大小 " + file.length() + " 字节");

        // 第二次：文件已存在 -> 再读一遍
        TabletopGameConfig second = create(file);
        System.out.println("[2] 二次回读      OK   minStartBalance="
                + second.getGambling().getMinStartBalance());

        String text = new String(Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8);
        String[] lines = text.split("\r?\n", -1);
        System.out.println("[3] 生成内容（行号从 1 起）：");
        for (int i = 0; i < lines.length; i++) {
            System.out.printf("    %2d | %s%n", i + 1, lines[i]);
        }

        // 额外检查：每一行要么空、要么以 # 开头、要么是缩进一致的 key: value
        int bad = 0;
        for (int i = 0; i < lines.length; i++) {
            String s = lines[i];
            if (s.trim().isEmpty() || s.trim().startsWith("#")) {
                continue;
            }
            if (!s.contains(":")) {
                System.out.println("    !! 第 " + (i + 1) + " 行缺冒号：" + s);
                bad++;
            }
        }
        System.out.println(bad == 0 ? "[4] 逐行结构检查 OK" : "[4] 逐行结构检查发现 " + bad + " 处问题");
        if (bad > 0) {
            System.exit(2);
        }
    }

    private static TabletopGameConfig create(File file) {
        return ConfigManager.create(TabletopGameConfig.class, it -> {
            it.withConfigurer(new YamlSnakeYamlConfigurer());
            it.withBindFile(file);
            it.saveDefaults();
            it.load(true);
        });
    }
}
