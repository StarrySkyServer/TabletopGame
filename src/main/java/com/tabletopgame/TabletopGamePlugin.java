package com.tabletopgame;

import cn.nukkit.command.Command;
import cn.nukkit.command.CommandSender;
import cn.nukkit.entity.custom.EntityManager;
import cn.nukkit.inventory.ShapedRecipe;
import cn.nukkit.item.Item;
import cn.nukkit.plugin.PluginBase;
import com.tabletopgame.board.GoBoard13Block;
import com.tabletopgame.board.GoBoard19BigBlock;
import com.tabletopgame.board.GoBoard19Block;
import com.tabletopgame.board.GoBoard9Block;
import com.tabletopgame.board.OthelloBoardBlock;
import com.tabletopgame.board.TabletopGameBoard3x3Block;
import com.tabletopgame.board.TabletopGameBoardBlock;
import com.tabletopgame.board.UnoTableBlocks;
import com.tabletopgame.board.XiangqiBoardBlock;
import com.tabletopgame.command.TabletopGameCommand;
import com.tabletopgame.entity.GoStoneBlackEntity;
import com.tabletopgame.entity.GoStoneWhiteEntity;
import com.tabletopgame.entity.OthelloDiscEntity;
import com.tabletopgame.entity.TabletopGameStoneBlackEntity;
import com.tabletopgame.entity.TabletopGameStoneWhiteEntity;
import com.tabletopgame.entity.UnoClickBoxEntity;
import com.tabletopgame.entity.UnoTableEntity;
import com.tabletopgame.entity.XiangqiPieceEntity;
import com.tabletopgame.game.GoManager;
import com.tabletopgame.game.OthelloManager;
import com.tabletopgame.game.TabletopGameManager;
import com.tabletopgame.game.UnoManager;
import com.tabletopgame.game.XiangqiManager;
import com.tabletopgame.item.GoBoard13Item;
import com.tabletopgame.item.GoBoard19BigItem;
import com.tabletopgame.item.GoBoard19Item;
import com.tabletopgame.item.GoBoard9Item;
import com.tabletopgame.item.LocatorItem;
import com.tabletopgame.item.OthelloBoardItem;
import com.tabletopgame.item.TabletopGameBoard3x3Item;
import com.tabletopgame.item.TabletopGameBoardItem;
import com.tabletopgame.item.UnoTableItem;
import com.tabletopgame.item.UnoTableRecipe;
import com.tabletopgame.item.XiangqiBoardItem;

/**
 * 五子棋插件入口。
 * <p>
 * 自定义实体、方块、物品必须在 {@code onLoad()} 中注册：此时 CustomBlockManager 已初始化
 * 但注册表尚未关闭，且早于 {@code EntityProperty.buildPacket()}，属性才能同步到客户端。
 */
public class TabletopGamePlugin extends PluginBase {

    private TabletopGameManager manager;
    private XiangqiManager xiangqiManager;
    private OthelloManager othelloManager;
    private GoManager goManager;
    private UnoManager unoManager;

    /** 已注册的 UNO 牌桌合成配方（null = 当前未注册）；由 {@link #syncUnoRecipe()} 维护。 */
    private ShapedRecipe unoRecipe;

    /** /tabletopgame 命令处理器（命令逻辑抽到 {@link com.tabletopgame.command.TabletopGameCommand}）。 */
    private TabletopGameCommand commandHandler;

    /** 当前插件主管理器（含全局配置），供设置表单等入口获取。 */
    public TabletopGameManager getManager() {
        return manager;
    }

    @Override
    public void onLoad() {
        TabletopGameStoneBlackEntity.registerProperties();
        EntityManager.get().registerDefinition(TabletopGameStoneBlackEntity.DEF);
        TabletopGameStoneWhiteEntity.registerProperties();
        EntityManager.get().registerDefinition(TabletopGameStoneWhiteEntity.DEF);
        XiangqiPieceEntity.registerProperties();
        EntityManager.get().registerDefinition(XiangqiPieceEntity.DEF);
        OthelloDiscEntity.registerProperties();
        EntityManager.get().registerDefinition(OthelloDiscEntity.DEF);
        GoStoneBlackEntity.registerProperties();
        EntityManager.get().registerDefinition(GoStoneBlackEntity.DEF);
        GoStoneWhiteEntity.registerProperties();
        EntityManager.get().registerDefinition(GoStoneWhiteEntity.DEF);
        // UNO 牌桌：一个实体承载整桌（21 个整型属性），必须在任何实体生成前注册
        UnoTableEntity.registerProperties();
        EntityManager.get().registerDefinition(UnoTableEntity.DEF);
        // 隐形载体实体：不渲染、碰撞箱 0.001；同时承载「悬浮倒计时」牌子（见 UnoClickBoxEntity）
        EntityManager.get().registerDefinition(UnoClickBoxEntity.DEF);
        TabletopGameBoardBlock.register();
        TabletopGameBoard3x3Block.register();
        XiangqiBoardBlock.register();
        OthelloBoardBlock.register();
        GoBoard9Block.register();
        GoBoard13Block.register();
        GoBoard19Block.register();
        GoBoard19BigBlock.register();
        UnoTableBlocks.register();
        Item.registerCustomItem(TabletopGameBoardItem.class);
        Item.registerCustomItem(TabletopGameBoard3x3Item.class);
        Item.registerCustomItem(XiangqiBoardItem.class);
        Item.registerCustomItem(OthelloBoardItem.class);
        Item.registerCustomItem(GoBoard9Item.class);
        Item.registerCustomItem(GoBoard13Item.class);
        Item.registerCustomItem(GoBoard19Item.class);
        Item.registerCustomItem(GoBoard19BigItem.class);
        Item.registerCustomItem(UnoTableItem.class);
        // 「定位器」：UNO 牌桌的持握道具，手持它右键能保证服务端收到信号（见 LocatorItem）
        Item.registerCustomItem(LocatorItem.class);
        getLogger().info("已注册自定义实体 " + TabletopGameStoneBlackEntity.IDENTIFIER
                + " / " + TabletopGameStoneWhiteEntity.IDENTIFIER
                + " / " + XiangqiPieceEntity.IDENTIFIER
                + " / " + OthelloDiscEntity.IDENTIFIER
                + " / " + GoStoneBlackEntity.IDENTIFIER
                + " / " + GoStoneWhiteEntity.IDENTIFIER
                + " / " + UnoTableEntity.IDENTIFIER
                + " / " + UnoClickBoxEntity.IDENTIFIER
                + "、道具 " + LocatorItem.IDENTIFIER
                + "、方块 " + TabletopGameBoardBlock.IDENTIFIER + " / " + TabletopGameBoard3x3Block.IDENTIFIER
                + " / " + XiangqiBoardBlock.IDENTIFIER
                + " / " + OthelloBoardBlock.IDENTIFIER
                + " / " + GoBoard9Block.IDENTIFIER
                + " / " + GoBoard13Block.IDENTIFIER
                + " / " + GoBoard19Block.IDENTIFIER
                + " / " + GoBoard19BigBlock.IDENTIFIER
                + " / " + UnoTableBlocks.CENTER
                + "、物品 " + TabletopGameBoardItem.IDENTIFIER + " / " + TabletopGameBoard3x3Item.IDENTIFIER
                + " / " + XiangqiBoardItem.IDENTIFIER
                + " / " + OthelloBoardItem.IDENTIFIER
                + " / " + GoBoard9Item.IDENTIFIER
                + " / " + GoBoard13Item.IDENTIFIER
                + " / " + GoBoard19Item.IDENTIFIER
                + " / " + GoBoard19BigItem.IDENTIFIER
                + " / " + UnoTableItem.IDENTIFIER);
    }

    @Override
    public void onEnable() {
        this.manager = new TabletopGameManager(this);
        this.commandHandler = new TabletopGameCommand(this);
        // 配置变更后同步 UNO 牌桌配方（见 syncUnoRecipe），让 reload 也能即时生效
        this.manager.setConfigListener(this::syncUnoRecipe);
        // 先加载配置，保证后续 tick 的范围检测能读到玩家识别半径（加载完即触发一次配方同步）
        this.manager.loadConfig();
        getServer().getPluginManager().registerEvents(this.manager, this);
        getServer().getScheduler().scheduleRepeatingTask(this, this.manager::tick, 5);
        // 插件在 STARTUP 阶段启用，此时关卡还没加载，等关卡就绪后由 tick 恢复已保存的棋盘
        this.manager.requestLoad();

        // 中国象棋：复用五子棋的配置（玩家识别半径），存档走独立文件
        this.xiangqiManager = new XiangqiManager(this, this.manager);
        getServer().getPluginManager().registerEvents(this.xiangqiManager, this);
        getServer().getScheduler().scheduleRepeatingTask(this, this.xiangqiManager::tick, 5);
        this.xiangqiManager.requestLoad();

        // 黑白棋（奥赛罗）：复用五子棋的配置，存档走独立文件
        this.othelloManager = new OthelloManager(this, this.manager);
        getServer().getPluginManager().registerEvents(this.othelloManager, this);
        getServer().getScheduler().scheduleRepeatingTask(this, this.othelloManager::tick, 5);
        this.othelloManager.requestLoad();

        // 围棋：复用五子棋的配置，存档走独立文件
        this.goManager = new GoManager(this, this.manager);
        getServer().getPluginManager().registerEvents(this.goManager, this);
        getServer().getScheduler().scheduleRepeatingTask(this, this.goManager::tick, 5);
        this.goManager.requestLoad();

        // UNO：复用同一份配置（半径 / 菜单锁 / 抽水），存档走 uno_tables.yml
        this.unoManager = new UnoManager(this, this.manager);
        getServer().getPluginManager().registerEvents(this.unoManager, this);
        getServer().getScheduler().scheduleRepeatingTask(this, this.unoManager::tick, 5);
        // 定位器绿点：**每 tick** 补一颗粒子（粒子寿命 0.18 秒）→ 常驻不闪
        //（需求「激光笔不是那种闪烁的那种效果，是要常驻显示」，见 UnoManager#tickLocatorDots）
        getServer().getScheduler().scheduleRepeatingTask(this, this.unoManager::tickLocatorDots, 1);
        this.unoManager.requestLoad();
        getLogger().info("TabletopGamePlugin 已启用");
    }

    /**
     * 按配置同步「UNO 牌桌物品是否可合成」。
     * <p>
     * {@code unoTableCraftable=false}（默认）时保证工作台里没有任何 UNO 牌桌配方，
     * 牌桌只能由 OP 用 {@code /tabletopgame uno} 发放；改为 true 后（编辑 config.yml 再
     * {@code /tabletopgame reload}）即为 3 个青色地毯 + 3 个深色橡木原木 + 3 个橡木板。
     * <p>
     * 内部记录已注册的那个 {@link ShapedRecipe} 实例，因此本方法可反复调用而不会重复注册
     * （{@link cn.nukkit.inventory.CraftingManager#registerRecipe} 不是幂等的）。
     */
    private void syncUnoRecipe() {
        boolean want = this.manager != null
                && this.manager.getConfig() != null
                && this.manager.getConfig().isUnoTableCraftable();
        if (want == (this.unoRecipe != null)) {
            return;
        }
        if (want) {
            this.unoRecipe = UnoTableRecipe.create();
            getServer().getCraftingManager().registerRecipe(this.unoRecipe);
            getLogger().info("已注册 UNO 牌桌合成配方（unoTableCraftable=true，青色地毯版）。");
        } else {
            boolean removed = getServer().getCraftingManager().unregisterRecipe(this.unoRecipe);
            this.unoRecipe = null;
            getLogger().info("已注销 UNO 牌桌合成配方（unoTableCraftable=false，removed=" + removed + "）。");
        }
    }

    @Override
    public void onDisable() {
        if (this.manager != null) {
            // 关服兜底：同步等待写盘完成
            this.manager.saveNow();
        }
        if (this.xiangqiManager != null) {
            this.xiangqiManager.saveNow();
        }
        if (this.othelloManager != null) {
            this.othelloManager.saveNow();
        }
        if (this.goManager != null) {
            this.goManager.saveNow();
        }
        if (this.unoManager != null) {
            this.unoManager.saveNow();
        }
        getLogger().info("TabletopGamePlugin 已关闭");
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        return this.commandHandler.onCommand(sender, command, label, args);
    }
}