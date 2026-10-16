package com.tabletopgame.ui;

import cn.nukkit.Player;
import cn.nukkit.Server;
import cn.nukkit.form.element.ElementInput;
import cn.nukkit.form.element.ElementLabel;
import cn.nukkit.form.handler.FormResponseHandler;
import cn.nukkit.form.window.FormWindowCustom;
import cn.nukkit.plugin.Plugin;
import com.tabletopgame.TabletopGamePlugin;
import com.tabletopgame.config.TabletopGameConfig;
import com.tabletopgame.game.TabletopGameManager;

import java.util.Locale;

/**
 * 插件设置表单（仅 OP）：把原 config.yml 的可调项放进表单实时调节。
 * <p>
 * 每个输入框留空即保持当前值；提交后立即生效（半径缓存同步刷新）并写回 config.yml。
 * 数值不合法时提示并重新打开表单。
 */
public final class SettingsMenu {

    /** 表单元素下标：0 为说明标签，1~5 为五个输入框。 */
    private static final int IDX_RANGE = 1;
    private static final int IDX_LOCK = 2;
    private static final int IDX_CUT = 3;
    private static final int IDX_MIN_BET = 4;
    private static final int IDX_MAX_BET = 5;

    private SettingsMenu() {
    }

    /** 从棋盘菜单「全局配置」入口进入的便捷打开方式：自行解析插件主管理器。 */
    public static void open(Player player) {
        Plugin plugin = Server.getInstance().getPluginManager().getPlugin("TabletopGame");
        if (plugin instanceof TabletopGamePlugin topp && topp.getManager() != null) {
            open(player, topp.getManager());
        } else {
            player.sendTip("§c插件尚未就绪，暂时无法打开设置。");
        }
    }

    /** 打开设置表单；非 OP 玩家直接拒绝。 */
    public static void open(Player player, TabletopGameManager manager) {
        if (!player.isOp()) {
            player.sendTip("§c只有 OP 可以修改插件设置。");
            return;
        }
        TabletopGameConfig config = manager.getConfig();
        TabletopGameConfig.Gambling gambling = config.getGambling();
        FormWindowCustom form = new FormWindowCustom("插件设置");
        form.addElement(new ElementLabel("§7留空表示保持当前值，提交后立即生效并自动保存。"));
        form.addElement(new ElementInput("玩家识别半径（格）", String.valueOf(config.getPlayerRange())));
        form.addElement(new ElementInput("菜单锁定超时（秒）", String.valueOf(config.getMenuLockSeconds())));
        form.addElement(new ElementInput("赌博抽水（%，0~100）", String.valueOf(gambling.normalizedCut())));
        form.addElement(new ElementInput("最小下注金额", String.valueOf(gambling.normalizedMinBet())));
        form.addElement(new ElementInput("最大下注金额", String.valueOf(gambling.normalizedMaxBet())));
        form.setSubmitButtonText("保存并生效");
        form.addHandler(FormResponseHandler.withoutPlayer(ignored -> process(player, manager, form)));
        player.showFormWindow(form);
    }

    /** 校验并应用提交结果；不合法时提示并重开设置表单。 */
    private static void process(Player player, TabletopGameManager manager, FormWindowCustom form) {
        if (form.wasClosed()) {
            return;
        }
        TabletopGameConfig config = manager.getConfig();
        TabletopGameConfig.Gambling gambling = config.getGambling();
        Double range = number(form, IDX_RANGE, config.getPlayerRange());
        Integer lock = integer(form, IDX_LOCK, config.getMenuLockSeconds());
        Double cut = number(form, IDX_CUT, gambling.normalizedCut());
        Double minBet = number(form, IDX_MIN_BET, gambling.normalizedMinBet());
        Double maxBet = number(form, IDX_MAX_BET, gambling.normalizedMaxBet());
        String error = null;
        if (range == null || lock == null || cut == null || minBet == null || maxBet == null) {
            error = "§c数值格式不正确：只能输入数字。";
        } else if (range <= 0) {
            error = "§c玩家识别半径必须大于 0。";
        } else if (lock < 1) {
            error = "§c菜单锁定超时至少 1 秒。";
        } else if (cut < 0 || cut > 100) {
            error = "§c抽水比例需在 0 ~ 100 之间。";
        } else if (minBet < 0 || maxBet < minBet) {
            error = "§c下注区间不合法：金额不能为负，且最大值不能小于最小值。";
        }
        if (error != null) {
            player.sendTip(error);
            open(player, manager);
            return;
        }
        manager.applySettings(range, lock, cut, minBet, maxBet);
        player.sendTip(String.format(Locale.ROOT,
                "§a设置已生效并保存：半径 %s 格；菜单锁定 %d 秒；抽水 %s%%，下注 %s ~ %s。",
                range, lock, cut, minBet, maxBet));
    }

    /** 读取指定下标的输入框并解析为小数；留空取默认值，格式错误返回 null。 */
    private static Double number(FormWindowCustom form, int index, double fallback) {
        String text = text(form, index);
        if (text.isEmpty()) {
            return fallback;
        }
        try {
            return Double.parseDouble(text);
        } catch (NumberFormatException e) {
            return null;
        }
    }

    /** 读取指定下标的输入框并解析为整数；留空取默认值，格式错误返回 null。 */
    private static Integer integer(FormWindowCustom form, int index, int fallback) {
        String text = text(form, index);
        if (text.isEmpty()) {
            return fallback;
        }
        try {
            return Integer.parseInt(text);
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private static String text(FormWindowCustom form, int index) {
        String value = form.getResponse().getInputResponse(index);
        return value == null ? "" : value.trim();
    }
}
