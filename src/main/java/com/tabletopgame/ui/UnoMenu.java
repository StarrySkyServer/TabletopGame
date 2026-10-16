package com.tabletopgame.ui;

import cn.nukkit.Player;
import com.tabletopgame.ui.Custom;
import com.tabletopgame.ui.Simple;
import com.tabletopgame.ai.UnoAi;
import com.tabletopgame.game.UnoTable;

import java.util.Locale;
import java.util.UUID;

/**
 * UNO 牌桌菜单：玩家在表单里<b>自选座位</b>（东/南/西/北 = P1..P4），
 * 也可以按三档补充 / 清除人机。
 *
 * <p>状态机（对应 {@link UnoTable.TablePhase}）：
 * <ul>
 *     <li>{@code WAITING} 未入座：4 个「坐X位」按钮（只列空位）+ 三档「加人机」+「清除人机」
 *     +「UNO 规则」+（仅 OP）「全局配置」；</li>
 *     <li>{@code WAITING} 已入座：三档「加人机」+「开始游戏」（夹在「加人机 · 高级」与
 *     「清除人机」之间；座位满时即「清除人机」的上面）+「清除人机」+（仅第一入座者）「设置倍数 k」
 *     （默认 0 = 免费局，仅可填 0~1000 的整数）+「托管 / 取消托管」+「退出牌桌」；</li>
 *     <li>{@code DEALER_DRAW} / {@code PLAYING}：不弹菜单（开局时已统一关闭），
 *     点牌桌直接走世界内按钮；</li>
 *     <li>{@code SETTLED}：「下一局」+「托管 / 取消托管」+「退出牌桌」。</li>
 * </ul>
 *
 * <p>菜单不提供「刷新」按钮：入座 / 加人机 / 清除人机 / 离座都会经
 * {@link com.tabletopgame.game.UnoManager#refreshSeatMenus} 自动刷新在座玩家的表单，
 * 与四种棋盘（五子棋 / 象棋 / 黑白棋 / 围棋）同一套「有人入座即自动刷新」的机制。
 *
 * <p>0 人入座的菜单是独占的（{@code menuLockSeconds}，默认 30 秒）：打开时校验占用权，
 * 每个按钮动作执行前再用 {@link UnoTable#holdsMenu} 校验一次并续期，
 * 保证第二个人不能同时操作，超时或被接管后旧表单立即失效。
 */
public final class UnoMenu {

    /** 人机档位名（下标 + {@link UnoAi#LEVEL_EASY} 即档位）。 */
    private static final String[] AI_LEVELS = {"初级", "中级", "高级"};

    private UnoMenu() {
    }

    /** 关闭玩家当前打开的表单（若有）。 */
    public static void closeCurrentForm(Player player) {
        if (!player.formWindows.isEmpty()) {
            player.closeFormWindows();
        }
    }

    public static void open(Player player, UnoTable table) {
        closeCurrentForm(player);
        UUID id = player.getUniqueId();
        int mySeat = table.seatOf(id);
        // 0 人入座时菜单独占
        if (mySeat < 0 && table.occupiedSeats() == 0 && !table.tryAcquireMenu(player)) {
            player.sendTip("§c有人正在操作该牌桌，请稍候。");
            return;
        }
        Simple form = new Simple("UNO", table.statusText(player));
        if (mySeat >= 0) {
            buildSeated(form, player, table);
        } else {
            buildVisitor(form, player, table);
        }
        if (form.buttonCount() == 0) {
            return;
        }
        if (table.occupiedSeats() == 0) {
            form.onClose(() -> table.releaseMenu(player));
        }
        form.show(player);
    }

    /** 从子表单返回上级菜单：仅在仍持有「0 人入座」菜单占用权时重新弹出。 */
    public static void reopen(Player player, UnoTable table) {
        if (table.occupiedSeats() == 0 && !table.holdsMenu(player)) {
            return;
        }
        open(player, table);
    }

    /** 0 人入座菜单的动作级校验。 */
    private static boolean checkMenu(Player player, UnoTable table) {
        if (table.holdsMenu(player)) {
            return true;
        }
        player.sendTip("§c该菜单已失效或被他人接管，请重新点击牌桌。");
        return false;
    }

    // ------------------------------------------------------------------
    // 未入座
    // ------------------------------------------------------------------

    private static void buildVisitor(Simple form, Player player, UnoTable table) {
        if (table.occupiedSeats() >= 4) {
            player.sendTip("§c座位已满（4 人），无法加入。");
            return;
        }
        for (int s = 0; s < 4; s++) {
            if (table.isOccupied(s)) {
                continue;
            }
            final int seat = s;
            form.add("坐" + UnoTable.seatLabel(seat), () -> {
                if (!checkMenu(player, table)) {
                    return;
                }
                String err = table.join(player, seat);
                if (err != null) {
                    player.sendTip("§c" + err);
                    table.laterOpen(player);
                }
            });
        }
        addBotButtons(form, player, table);
        addClearBotsButton(form, player, table);
        addRuleButton(form, player, table);
        addSettingsButton(form, player, table);
    }

    // ------------------------------------------------------------------
    // 已入座
    // ------------------------------------------------------------------

    private static void buildSeated(Simple form, Player player, UnoTable table) {
        UnoTable.TablePhase phase = table.getPhase();
        if (phase == UnoTable.TablePhase.WAITING) {
            addBotButtons(form, player, table);
            // 「开始游戏」夹在「加人机 · 高级」与「清除人机」中间（需求原话）；
            // 座位满时没有加人机按钮，于是它自然落在「清除人机」上面。
            if (table.occupiedSeats() >= 2) {
                form.add("开始游戏", () -> {
                    String err = table.startRound();
                    if (err != null) {
                        player.sendTip("§c" + err);
                    }
                });
            }
            addClearBotsButton(form, player, table);
            if (table.isFirstJoiner(player.getUniqueId())) {
                form.add("设置倍数 k（当前 " + fmt(table.getCoefficient()) + "）",
                        () -> table.laterOpen(() -> openCoefficientInput(player, table)));
            }
        } else if (phase == UnoTable.TablePhase.SETTLED) {
            form.add("下一局", () -> table.laterOpen(() -> nextRound(player, table)));
        }
        // 托管：像斗地主插件那样，点了就由系统按机器人逻辑代打（再点一次取消）。
        // 断线重连 / 离座都会自动取消，不会「人回来了还被代打」。
        form.add(table.isTrusted(table.seatOf(player.getUniqueId())) ? "取消托管" : "托管（系统代打）",
                () -> {
                    String err = table.toggleTrust(player);
                    if (err != null) {
                        player.sendTip("§c" + err);
                    }
                });
        form.add("退出牌桌", () -> table.leave(player));
        // 不再提供「刷新」按钮：座位变化（入座 / 加人机 / 清除人机 / 离座）时
        // UnoManager#refreshSeatMenus 会自动关旧表单再重弹，与四种棋盘同一套机制。
    }

    /** 结算后开下一局：失败（例如座位不足）时提示并重开菜单。 */
    private static void nextRound(Player player, UnoTable table) {
        String err = table.startRound();
        if (err != null) {
            player.sendTip("§c" + err);
            table.laterOpen(player);
        }
    }

    // ------------------------------------------------------------------
    // 共用按钮
    // ------------------------------------------------------------------

    /** 三档「加人机」：每点一次往下一个空位补一个机器人。 */
    private static void addBotButtons(Simple form, Player player, UnoTable table) {
        if (table.occupiedSeats() >= 4) {
            return;
        }
        for (int i = 0; i < AI_LEVELS.length; i++) {
            final int level = i;
            form.add("加人机 · " + AI_LEVELS[i], () -> {
                if (table.occupiedSeats() > 0 && !checkMenu(player, table)) {
                    return;
                }
                String err = table.addBot(level);
                if (err != null) {
                    player.sendTip("§c" + err);
                }
            });
        }
    }

    private static void addClearBotsButton(Simple form, Player player, UnoTable table) {
        if (!table.hasBots()) {
            return;
        }
        form.add("清除人机", () -> {
            if (table.occupiedSeats() > 0 && !checkMenu(player, table)) {
                return;
            }
            String err = table.clearBots();
            if (err != null) {
                player.sendTip("§c" + err);
            }
        });
    }

    /**
     * 「UNO 规则」入口：仅「0 人入座」时出现。
     * <p>点进去即视作离开「0 人入座」页面：立即释放菜单占用锁，其他人可正常操作牌桌。
     */
    private static void addRuleButton(Simple form, Player player, UnoTable table) {
        form.add("UNO 规则", () -> {
            if (checkMenu(player, table)) {
                table.releaseMenu(player);
                table.laterOpen(() -> openRule(player, table));
            }
        });
    }

    /** 「全局配置」入口：仅 OP 在「0 人入座」菜单可见。 */
    private static void addSettingsButton(Simple form, Player player, UnoTable table) {
        if (!player.isOp()) {
            return;
        }
        form.add("全局配置", () -> {
            if (checkMenu(player, table)) {
                table.releaseMenu(player);
                table.laterOpen(() -> com.tabletopgame.ui.SettingsMenu.open(player));
            }
        });
    }

    // ------------------------------------------------------------------
    // 子表单
    // ------------------------------------------------------------------

    /** 「UNO 规则」表单：只展示说明文字，仅一个「退出」按钮，关闭后不返回上一级。 */
    private static void openRule(Player player, UnoTable table) {
        Simple form = new Simple("UNO · 规则",
                "§f【目标】\n"
                        + "§7· 谁先打完手上的牌谁获胜，其余各家按剩余手牌计分；\n"
                        + "§7· 每人起手 7 张，中间牌堆与弃牌堆各一堆。\n\n"
                        + "§f【出牌】\n"
                        + "§7· 只能出与当前颜色相同、或与顶牌数字/功能相同的牌；\n"
                        + "§7· 无牌可出就摸一张，摸到的牌若能出可直接打出，也可以选择跳过；\n"
                        + "§7· 野牌（Wild / Wild+4）可随时打出，但需先指定颜色。\n\n"
                        + "§f【功能牌】\n"
                        + "§7· 跳过：下家停一轮；\n"
                        + "§7· 反转：出牌方向反向（2 人局等同跳过）；\n"
                        + "§7· +2：下家摸 2 张并停一轮；\n"
                        + "§7· Wild+4：指定颜色，下家摸 4 张并停一轮（手中还有当前颜色时不可出）。\n\n"
                        + "§f【座次与先手】\n"
                        + "§7· 座位东/南/西/北对应 P1/P2/P3/P4，可自选；\n"
                        + "§7· 开场每人抽一张比大小定庄（功能牌与野牌算 0，并列最大则重抽）；\n"
                        + "§7· 庄家左手边先手，顺时针轮转。\n\n"
                        + "§f【UNO】\n"
                        + "§7· 出到只剩最后一张牌时自动喊 UNO；\n"
                        + "§f【结算】\n"
                        + "§7· 各家按剩余手牌分 × 本桌倍数 k 付给赢家；\n"
                        + "§7· k 只能是 0~1000 的整数，默认 0：k = 0 为免费局，不扣钱也不抽水；\n"
                        + "§7· 扣款「扣到零为止」：应付超过余额时只扣到 0，余额不会变负；\n"
                        + "§7· 各家§f实扣额§7先合计成奖池，再整体抽水，税后金额归赢家；\n"
                        + "§7· k > 0 时开局要求每位玩家余额大于等于配置门槛（默认 10000）。");
        form.add("退出", () -> {
        });
        form.show(player);
    }

    /** 倍数 k 输入表单；直接关闭时回到牌桌菜单。 */
    private static void openCoefficientInput(Player player, UnoTable table) {
        new Custom("UNO · 倍数 k")
                .label("请输入本桌倍数 k（0 ~ " + (long) UnoTable.MAX_COEFFICIENT
                        + " 的整数，默认 0）\n"
                        + "· k = 0：免费局，不扣钱、也没有抽水；\n"
                        + "· k > 0：赢家收「其余各家剩余手牌分 × k」的实扣合计，再扣官方抽水。")
                .input("倍数 k", fmt(table.getCoefficient()))
                .submit("确认")
                .onSubmit(text -> table.laterOpen(() -> handleCoefficient(player, table, text)))
                .onClose(() -> table.laterOpen(player))
                .show(player);
    }

    private static void handleCoefficient(Player player, UnoTable table, String text) {
        Double k = parseAmount(text);
        if (k == null) {
            player.sendTip("§c倍数格式不正确：只能输入 0 ~ "
                    + (long) UnoTable.MAX_COEFFICIENT + " 的整数。");
            table.laterOpen(player);
            return;
        }
        String err = table.setCoefficient(player, k);
        if (err != null) {
            player.sendTip("§c" + err);
        }
        table.laterOpen(player);
    }

    /** 解析倍数：只接受 0 ~ {@link UnoTable#MAX_COEFFICIENT} 的整数（不接受小数、符号）。 */
    private static Double parseAmount(String text) {
        if (text == null || !text.trim().matches("\\d+")) {
            return null;
        }
        try {
            long value = Long.parseLong(text.trim());
            return value <= (long) UnoTable.MAX_COEFFICIENT ? (double) value : null;
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private static String fmt(double value) {
        return value == Math.rint(value)
                ? Long.toString((long) Math.rint(value))
                : String.format(Locale.ROOT, "%.2f", value);
    }
}
