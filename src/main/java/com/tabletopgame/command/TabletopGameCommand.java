package com.tabletopgame.command;

import cn.nukkit.Player;
import cn.nukkit.command.Command;
import cn.nukkit.command.CommandSender;
import cn.nukkit.item.Item;
import com.tabletopgame.TabletopGamePlugin;
import com.tabletopgame.item.GoBoard13Item;
import com.tabletopgame.item.GoBoard19BigItem;
import com.tabletopgame.item.GoBoard19Item;
import com.tabletopgame.item.GoBoard9Item;
import com.tabletopgame.item.OthelloBoardItem;
import com.tabletopgame.item.TabletopGameBoard3x3Item;
import com.tabletopgame.item.TabletopGameBoardItem;
import com.tabletopgame.item.UnoTableItem;
import com.tabletopgame.item.XiangqiBoardItem;
import com.tabletopgame.ui.SettingsMenu;

/**
 * {@code /tabletopgame} 命令处理器：settings / reload / 发放各棋棋盘与 UNO 牌桌物品。
 * <p>
 * 从 {@link TabletopGamePlugin} 抽出独立成 {@code command} 包，符合 Nukkit-MOT / EconomyAPI 的
 * 「命令与插件主类分离」职责划分。命令仅做参数分发，具体逻辑委托给 {@code TabletopGameManager}。
 */
public final class TabletopGameCommand {

    private final TabletopGamePlugin plugin;

    public TabletopGameCommand(TabletopGamePlugin plugin) {
        this.plugin = plugin;
    }

    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        // /tabletopgame settings：打开插件设置表单（OP，实时生效并写回 config.yml）
        if (args.length > 0 && "settings".equalsIgnoreCase(args[0])) {
            if (!sender.isOp()) {
                sender.sendMessage("§c你没有权限使用该命令。");
                return true;
            }
            if (!(sender instanceof Player player)) {
                sender.sendMessage("§c插件设置需由 OP 玩家在游戏内执行 /tabletopgame settings（打开表单界面实时调节）。");
                return true;
            }
            SettingsMenu.open(player, plugin.getManager());
            return true;
        }

        // /tabletopgame reload：重载配置文件（OP 或控制台）
        if (args.length > 0 && "reload".equalsIgnoreCase(args[0])) {
            if (!sender.isOp()) {
                sender.sendMessage("§c你没有权限使用该命令。");
                return true;
            }
            sender.sendMessage("§7正在重载配置…");
            plugin.getManager().reloadConfig(sender);
            return true;
        }

        // 其余用法：发放棋盘物品，仅玩家可用
        if (!(sender instanceof Player player)) {
            sender.sendMessage("§c该命令只能由玩家执行（重载配置请使用 /tabletopgame reload）。");
            return true;
        }
        if (!player.isOp()) {
            player.sendMessage("§c你没有权限使用该命令。");
            return true;
        }
        String arg = args.length > 0 ? args[0].toLowerCase(java.util.Locale.ROOT) : "";
        boolean medium = "3x3".equals(arg);
        boolean xiangqi = "xiangqi".equals(arg);
        boolean othello = "othello".equals(arg);
        boolean uno = "uno".equals(arg);
        Item board;
        String sizeLabel;
        if (uno) {
            board = new UnoTableItem();
            sizeLabel = "UNO 牌桌";
        } else if (xiangqi) {
            board = new XiangqiBoardItem();
            sizeLabel = "中国象棋";
        } else if (othello) {
            board = new OthelloBoardItem();
            sizeLabel = "黑白棋";
        } else if ("go9".equals(arg)) {
            board = new GoBoard9Item();
            sizeLabel = "围棋（9 路）";
        } else if ("go13".equals(arg)) {
            board = new GoBoard13Item();
            sizeLabel = "围棋（13 路）";
        } else if ("go19".equals(arg)) {
            board = new GoBoard19Item();
            sizeLabel = "围棋（19 路 · 3×3）";
        } else if ("go19big".equals(arg)) {
            board = new GoBoard19BigItem();
            sizeLabel = "围棋（19 路 · 4×4）";
        } else if (medium) {
            board = new TabletopGameBoard3x3Item();
            sizeLabel = "3×3";
        } else {
            board = new TabletopGameBoardItem();
            sizeLabel = "";
        }
        player.getInventory().addItem(board);
        player.sendMessage("§a已获得" + sizeLabel + "棋盘物品，对准地面右键即可放置。");
        return true;
    }
}
