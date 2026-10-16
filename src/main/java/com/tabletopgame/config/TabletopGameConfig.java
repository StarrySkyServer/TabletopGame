package com.tabletopgame.config;

import eu.okaeri.configs.OkaeriConfig;
import eu.okaeri.configs.annotation.Comment;
import eu.okaeri.configs.annotation.Header;

/**
 * 插件配置。字段默认值即首次运行生成的 config.yml 内容。
 * <p>
 * 推荐通过 {@code /tabletopgame settings} 表单调整（OP，实时生效并自动写回本文件）；
 * 手动编辑后也可用 {@code /tabletopgame reload} 重载。
 */
@Header({"TabletopGame 插件配置", "推荐用 /tabletopgame settings 表单调整（OP，实时生效并自动保存）；手动编辑后可用 /tabletopgame reload 重载"})
public class TabletopGameConfig extends OkaeriConfig {

    @Comment("玩家离开棋盘中心多少格后自动退出棋局（水平方向）")
    private double playerRange = 7.0;

    @Comment("0 人入座时菜单的独占超时（秒）。超时或持有者下线会自动释放占用，让给其他人；有人入座后不再有该兜底")
    private int menuLockSeconds = 30;

    @Comment({"UNO 牌桌物品是否可在工作台合成（默认 false = 不能合成，只能由 OP 用 /tabletopgame uno 发放）",
            "开启后配方为（青色地毯 x3 / 深色橡木原木 x3 / 橡木板 x3）：",
            "  青色地毯   青色地毯   青色地毯",
            "  深色橡木原木 深色橡木原木 深色橡木原木",
            "  橡木板     橡木板     橡木板"})
    private boolean unoTableCraftable = false;

    @Comment("赌博模式设置（仅玩家对玩家对局生效；本插件强依赖 EconomyAPI）")
    private Gambling gambling = new Gambling();

    public double getPlayerRange() {
        return playerRange;
    }

    public void setPlayerRange(double playerRange) {
        this.playerRange = playerRange;
    }

    /** 菜单独占超时秒数（至少 1 秒）。 */
    public int getMenuLockSeconds() {
        return Math.max(1, menuLockSeconds);
    }

    public void setMenuLockSeconds(int menuLockSeconds) {
        this.menuLockSeconds = menuLockSeconds;
    }

    /** UNO 牌桌物品是否可合成。false（默认）时不会向工作台注册任何配方。 */
    public boolean isUnoTableCraftable() {
        return unoTableCraftable;
    }

    public void setUnoTableCraftable(boolean unoTableCraftable) {
        this.unoTableCraftable = unoTableCraftable;
    }

    public Gambling getGambling() {
        return gambling;
    }

    /** 赌博模式：官方抽水比例与每局可下注金额区间。 */
    public static class Gambling extends OkaeriConfig {

        @Comment("官方每局抽水百分比（0~100，保留两位小数）。默认 1.0 即 1%；100 表示赢家也拿不到奖金")
        private double cut = 1.0;

        @Comment("每局可下注的最小金额")
        private double minBet = 1000.0;

        @Comment("每局可下注的最大金额")
        private double maxBet = 1000000.0;

        // 注意：多行注释必须用「数组」形式。写成单个字符串 + "\n" 时，
        // okaeri 只会给整串开头加 "#"，续行会裸输出成非法 YAML 键，导致配置解析失败、插件加载不起来。
        @Comment({"UNO 牌桌开设「按倍数结算」对局（倍数 k > 0）时，每位真人玩家开局前必须拥有的最低余额。",
                "余额必须【大于等于】该值才能开局，否则提示「无法开局」。k = 0 的免费局不受此限制。"})
        private double minStartBalance = 10000.0;

        public double getCut() {
            return cut;
        }

        public void setCut(double cut) {
            this.cut = cut;
        }

        public double getMinBet() {
            return minBet;
        }

        public void setMinBet(double minBet) {
            this.minBet = minBet;
        }

        public double getMaxBet() {
            return maxBet;
        }

        public void setMaxBet(double maxBet) {
            this.maxBet = maxBet;
        }

        public double getMinStartBalance() {
            return minStartBalance;
        }

        public void setMinStartBalance(double minStartBalance) {
            this.minStartBalance = minStartBalance;
        }

        /** UNO 按倍数结算的开局余额门槛（负数归零）。 */
        public double normalizedMinStartBalance() {
            return Math.max(0.0, Math.round(minStartBalance * 100.0) / 100.0);
        }

        /** 抽水比例：钳制到 0~100 并四舍五入保留两位小数。 */
        public double normalizedCut() {
            double c = Math.max(0.0, Math.min(100.0, cut));
            return Math.round(c * 100.0) / 100.0;
        }

        /** 每局最小下注金额（负数归零）。 */
        public double normalizedMinBet() {
            return Math.max(0.0, Math.round(minBet * 100.0) / 100.0);
        }

        /** 每局最大下注金额；若配置小于最小值则取最小值。 */
        public double normalizedMaxBet() {
            double max = Math.max(0.0, Math.round(maxBet * 100.0) / 100.0);
            return Math.max(max, normalizedMinBet());
        }
    }
}