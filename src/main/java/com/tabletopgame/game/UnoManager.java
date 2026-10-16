package com.tabletopgame.game;

import cn.nukkit.Player;
import cn.nukkit.Server;
import cn.nukkit.block.Block;
import cn.nukkit.event.EventHandler;
import cn.nukkit.event.EventPriority;
import cn.nukkit.event.Listener;
import cn.nukkit.event.block.BlockBreakEvent;
import cn.nukkit.event.player.PlayerInteractEntityEvent;
import cn.nukkit.event.player.PlayerInteractEvent;
import cn.nukkit.event.player.PlayerJoinEvent;
import cn.nukkit.event.player.PlayerQuitEvent;
import cn.nukkit.item.Item;
import cn.nukkit.level.Level;
import cn.nukkit.level.Sound;
import cn.nukkit.math.BlockFace;
import cn.nukkit.math.Vector3;
import cn.nukkit.plugin.PluginBase;
import com.tabletopgame.config.TabletopGameConfig;
import com.tabletopgame.game.TabletopGameManager;
import com.tabletopgame.storage.BoardStorage;
import com.tabletopgame.board.UnoTableBlocks;
import com.tabletopgame.entity.UnoClickBoxEntity;
import com.tabletopgame.entity.UnoTableEntity;
import com.tabletopgame.item.LocatorItem;
import com.tabletopgame.item.UnoTableItem;
import com.tabletopgame.ui.UnoMenu;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * 管理所有已放置的 UNO 牌桌：放置、破坏收回、菜单、交互、机器人派发与存档恢复。
 * <p>
 * 骨架对齐 {@link com.tabletopgame.game.XiangqiManager}：复用五子棋的全局配置
 * （玩家识别半径 / 菜单独占超时 / 赌博抽水比例），存档走独立文件 {@code uno_tables.yml}。
 * <p>
 * 与四棋的差别：UNO 牌桌是 <b>N 人（2..4）自由入座</b>的实时交互桌，没有轮次落子，
 * 因此不需要 {@code onMove} 落点高亮（准星 hover 逐表 tick 刷新即可），
 * 但需要把「破坏任意一格即整桌收回」与「右键牌桌 = 准星直接交互」都接过来。
 */
public class UnoManager implements Listener {

    /** 放置牌桌的冷却时间（毫秒）：一次点击可能触发多个交互事件，需去重。 */
    private static final long PLACE_COOLDOWN_MS = 500L;

    /** 当前存档文件名（YAML）。 */
    private static final String STORAGE_FILE = "uno_tables.yml";

    private final PluginBase plugin;

    /** 复用五子棋的全局配置（同一个 config.yml，不重复加载配置）。 */
    private final TabletopGameManager gameManager;

    private final Map<String, UnoTable> tables = new ConcurrentHashMap<>();
    private final Map<UUID, Long> placeCooldown = new HashMap<>();

    /** 每个玩家最近一次「已处理」右键的服务器 tick（见 claimClick：同 tick 去重）。 */
    private final Map<UUID, Integer> clickTicks = new ConcurrentHashMap<>();

    // ---- 定位器「激光」开关（蹲下 + 使用键切换，见 toggleLaser） ----

    /** 激光开关的防抖窗口（tick）：触屏按住「使用」键可能连发事务，窗口内只认一次。 */
    private static final int LASER_TOGGLE_COOLDOWN = 10;

    /** 关掉激光的玩家才出现在这里（默认开启）。 */
    private final Map<UUID, Boolean> laserSwitch = new ConcurrentHashMap<>();

    /** 上一次切换激光的 tick（防抖用）。 */
    private final Map<UUID, Integer> laserToggleTicks = new ConcurrentHashMap<>();

    /** 按关卡索引牌桌，右键命中与破坏时只需看玩家所在关卡。 */
    private final Map<Level, List<UnoTable>> tablesByLevel = new ConcurrentHashMap<>();

    /** 玩家 → 所在牌桌。 */
    private final Map<UUID, UnoTable> seatings = new ConcurrentHashMap<>();

    /** 牌桌增删后置位，下一次 tick 落盘，避免频繁写文件。 */
    private boolean dirty;

    /** 插件以 STARTUP 阶段启用，此时关卡尚未加载，需等关卡就绪后再恢复牌桌。 */
    private boolean loadPending;

    /** 首次恢复是否已完成。未完成前禁止写盘，避免用空数据覆盖存档。 */
    private boolean restored;

    /** 存档写盘线程：单线程串行执行，守护线程，关服不阻塞进程退出。 */
    private final ExecutorService saveExecutor = Executors.newSingleThreadExecutor(task -> {
        Thread thread = new Thread(task, "Uno-Save");
        thread.setDaemon(true);
        return thread;
    });

    public UnoManager(PluginBase plugin, TabletopGameManager gameManager) {
        this.plugin = plugin;
        this.gameManager = gameManager;
    }

    // ------------------------------------------------------------------
    // 配置 / 工具
    // ------------------------------------------------------------------

    /** 玩家识别半径。 */
    public double playerRange() {
        return gameManager.playerRange();
    }

    /** 插件配置（含赌博模式设置），供牌桌读取抽水比例。 */
    public TabletopGameConfig config() {
        return gameManager.getConfig();
    }

    /** 「0 人入座」菜单占用超时（毫秒），沿用配置 {@code menuLockSeconds}。 */
    long menuLockMs() {
        return gameManager.getConfig().getMenuLockSeconds() * 1000L;
    }

    /** 玩家显示名（离线后从牌桌记录里取，最后才回退到 UUID 前缀）。 */
    public String nameOf(UUID id) {
        if (id == null) {
            return "—";
        }
        Player p = Server.getInstance().getPlayer(id).orElse(null);
        if (p != null) {
            return p.getName();
        }
        UnoTable table = seatings.get(id);
        if (table != null) {
            int seat = table.seatOf(id);
            if (seat >= 0) {
                return table.seatName(seat);
            }
        }
        return id.toString().substring(0, 8);
    }

    /** 延后一 tick 在主线程执行，避免在表单回调中直接弹窗造成客户端窗口冲突。 */
    public void runLater(Runnable action) {
        Server.getInstance().getScheduler().scheduleDelayedTask(plugin, action, 1);
    }

    /** 延迟一 tick 重新弹出指定玩家的牌桌菜单。 */
    public void reopenMenu(Player player, UnoTable table) {
        runLater(() -> UnoMenu.reopen(player, table));
    }

    /** 打开牌桌菜单。 */
    public void openMenu(Player player, UnoTable table) {
        UnoMenu.open(player, table);
    }

    /**
     * 座位变化后刷新所有在座玩家的牌桌菜单：先关掉客户端上的旧表单，再延后一 tick 重弹，
     * 借客户端「新表单顶掉旧表单」完成自动切换。
     */
    public void refreshSeatMenus(UnoTable table) {
        if (table.getPhase() == UnoTable.TablePhase.PLAYING
                || table.getPhase() == UnoTable.TablePhase.DEALER_DRAW) {
            return;
        }
        for (UUID id : seatedIds(table)) {
            Player p = Server.getInstance().getPlayer(id).orElse(null);
            if (p == null) {
                continue;
            }
            UnoMenu.closeCurrentForm(p);
            reopenMenu(p, table);
        }
    }

    /** 开局时关闭所有在座玩家的牌桌表单。 */
    public void closeSeatMenus(UnoTable table) {
        for (UUID id : seatedIds(table)) {
            Player p = Server.getInstance().getPlayer(id).orElse(null);
            if (p != null) {
                UnoMenu.closeCurrentForm(p);
            }
        }
    }

    private List<UUID> seatedIds(UnoTable table) {
        List<UUID> out = new ArrayList<>(4);
        for (int s = 0; s < 4; s++) {
            Player p = table.onlineAt(s);
            if (p != null) {
                out.add(p.getUniqueId());
            }
        }
        if (out.isEmpty()) {
            UUID owner = table.menuHolderId();
            if (owner != null) {
                out.add(owner);
            }
        }
        return out;
    }

    /**
     * 确保背包里有一把「定位器」（没有才发）。
     * <p>
     * 需求（2026-10-15）：「开局，如果玩家背包没有这个东西自动发放，结束对局的话，自动回收」。
     * 发放入口只有 {@code UnoTable.startRound()}；回收见 {@link #takeLocator(Player)}。
     */
    public void ensureLocator(Player player) {
        for (Item item : player.getInventory().getContents().values()) {
            if (item instanceof LocatorItem) {
                return;
            }
        }
        player.getInventory().addItem(new LocatorItem());
    }

    /**
     * 回收「定位器」：清掉背包里所有同名道具（离桌 / 牌桌被拆除 / 老玩家残留 时调用）。
     * <p>只动 {@link LocatorItem}，不会碰到玩家的其他任何东西。
     */
    public void takeLocator(Player player) {
        Map<Integer, Item> contents = player.getInventory().getContents();
        List<Integer> hit = new ArrayList<>();
        for (Map.Entry<Integer, Item> e : contents.entrySet()) {
            if (e.getValue() instanceof LocatorItem) {
                hit.add(e.getKey());
            }
        }
        if (hit.isEmpty()) {
            return;
        }
        for (int slot : hit) {
            player.getInventory().clear(slot);
        }
        player.getInventory().sendContents(player);
    }

    /**
     * 该玩家的「定位器激光」是否开启（默认开）。
     * <p>手持定位器、准星压在牌 / 按钮上时，{@code UnoTable} 会沿视线在命中点放一颗白色光点；
     * 这里返回 false 时光点什么也不放（玩家用「蹲下 + 使用键」关掉了它）。
     */
    public boolean isLaserOn(Player player) {
        return !Boolean.FALSE.equals(laserSwitch.get(player.getUniqueId()));
    }

    /**
     * 是否处于「激光模式」：**蹲下 + 手持定位器**。
     * <p>
     * 需求（2026-10-15）：「激光笔新增一个机制，就是玩家蹲下的时候点使用键，
     * 只要没触发那些uno棋盘的东西，就变成激光的开关控制（用broadcastActionBar显示）」。
     * <p>
     * 为什么这条链路成立：手持物品按「使用」时，客户端一定会发「使用物品」事务，
     * MOT 的 {@code UseItemProcessor_v113} 收到后固定派发
     * {@code PlayerInteractEvent(RIGHT_CLICK_AIR)}（空手时反而可能什么都不发）——
     * 所以「蹲下 + 使用」在**任何地方**都能被服务端收到，不依赖准星打没打中方块。
     */
    private static boolean laserMode(Player player) {
        return player.isSneaking()
                && player.getInventory().getItemInHand() instanceof LocatorItem;
    }

    /**
     * 蹲下 + 使用键 → 切换激光开关，状态用**动作栏**（{@code sendTip}）回报给本人。
     * <p>
     * 只有当这次右键「没触发牌桌上任何东西」时才会走到这里：点到手牌 / 按钮仍然走棋盘的
     * 出牌逻辑（见三个交互入口里的 {@code laserMode} 分支）。0.5 秒防抖，避免触屏按住
     * 「使用」键时来回翻转。
     */
    private void toggleLaser(Player player) {
        int now = Server.getInstance().getTick();
        Integer last = laserToggleTicks.get(player.getUniqueId());
        if (last != null && now - last < LASER_TOGGLE_COOLDOWN) {
            return;
        }
        laserToggleTicks.put(player.getUniqueId(), now);
        boolean on = !isLaserOn(player);
        laserSwitch.put(player.getUniqueId(), on);
        player.sendTip(on ? "§a定位器激光 §7| §a已开启" : "§7定位器激光 §7| §8已关闭");
    }

    /** 玩家入座登记（由牌桌调用）。 */
    public void seat(UUID playerId, UnoTable table) {
        seatings.put(playerId, table);
    }

    /** 玩家离座登记（由牌桌调用）。 */
    public void unseat(UUID playerId) {
        seatings.remove(playerId);
    }

    public UnoTable getTableOf(UUID playerId) {
        return seatings.get(playerId);
    }

    /** 注册牌桌。 */
    public void registerTable(String key, UnoTable table) {
        tables.put(key, table);
        tablesByLevel.computeIfAbsent(table.getLevel(), k -> new ArrayList<>(4)).add(table);
    }

    /** 注销牌桌。 */
    public void unregisterTable(String key) {
        UnoTable table = tables.remove(key);
        if (table == null) {
            return;
        }
        List<UnoTable> list = tablesByLevel.get(table.getLevel());
        if (list != null) {
            list.remove(table);
            if (list.isEmpty()) {
                tablesByLevel.remove(table.getLevel());
            }
        }
    }

    public Map<String, UnoTable> getTables() {
        return tables;
    }

    /** 标记存档已变更，等待下一次 tick 统一保存。包级可见，供同包的 {@link UnoTable} 调用。 */
    void markDirty() {
        this.dirty = true;
    }

    // ------------------------------------------------------------------
    // 主循环
    // ------------------------------------------------------------------

    public void tick() {
        if (loadPending && !Server.getInstance().getLevels().isEmpty()) {
            loadPending = false;
            load();
        }
        if (dirty) {
            dirty = false;
            save();
        }
        if (tables.isEmpty()) {
            return;
        }
        for (UnoTable table : tables.values()) {
            table.tick();
        }
    }

    /**
     * 定位器激光点的常驻刷新：**每个游戏 tick** 调一次（见 {@code TabletopGamePlugin} 的调度）。
     * <p>
     * 2026-10-16：激光点已是模型薄片（不再补粒子），这里只做「每 tick 广播激光坐标」，
     * 20Hz 才跟得上准星扫动；无桌 / 无人手持定位器时由 {@link UnoTable#tickLocatorDots()}
     * 里的 early-exit 快速跳过，属性写入有缓存去重（值不变不发包），不会空转刷包。
     */
    public void tickLocatorDots() {
        if (tables.isEmpty()) {
            return;
        }
        for (UnoTable table : tables.values()) {
            table.tickLocatorDots();
        }
    }

    /** 关服：销毁所有牌桌（实体 close），不结算。 */
    public void shutdown() {
        for (UnoTable table : tables.values()) {
            table.destroy();
        }
        tables.clear();
        tablesByLevel.clear();
        seatings.clear();
    }

    // ------------------------------------------------------------------
    // 事件
    // ------------------------------------------------------------------

    @EventHandler
    public void onQuit(PlayerQuitEvent event) {
        Player player = event.getPlayer();
        placeCooldown.remove(player.getUniqueId());
        clickTicks.remove(player.getUniqueId());
        laserToggleTicks.remove(player.getUniqueId());
        UnoTable table = seatings.get(player.getUniqueId());
        if (table != null) {
            table.onDisconnect(player);
        }
        for (UnoTable other : tables.values()) {
            // 未入座但正占用「0 人入座」菜单的玩家离线：立即释放，避免他人被锁到超时
            other.releaseMenu(player.getUniqueId());
        }
    }

    /**
     * 上线兜底：没坐在任何牌桌上却带着「定位器」（上次被强踢 / 服务器重启前留下的）→ 收回。
     * <p>入座者不动：他们的定位器由牌桌在开局时补发、离桌时回收。
     */
    @EventHandler
    public void onJoin(PlayerJoinEvent event) {
        Player player = event.getPlayer();
        if (!seatings.containsKey(player.getUniqueId())) {
            takeLocator(player);
        }
    }

    /**
     * 右键：命中牌桌方块 → 入座则准星直接交互（未入座弹菜单）；
     * 手持牌桌物品点非牌桌方块 → 铺设 3x3 建桌。
     * <p>
     * 刻意不设置 {@code ignoreCancelled = true}：基岩触屏点击会走
     * {@code Level#useItemOn}，该路径可能因出生点保护在派发事件前取消事件，
     * 忽略已取消事件会导致出生点附近完全收不到回调。
     * <p>
     * <b>为什么还要收「右键空中」</b>：手牌是悬空在台面上方的（第一行底边离台面 0.26 格，
     * 第二行起更高），基岩客户端的准星只认<b>方块</b>——瞄第二行及以上的牌时打不到牌桌方块，
     * 客户端就只发 {@code RIGHT_CLICK_AIR}。以前只处理方块事件，于是「第二行的牌能选中
     * （悬停高亮是服务端自己算的）但点击没反应，要站高一格才能点中」（用户原话）。
     */
    @EventHandler(priority = EventPriority.HIGH)
    public void onInteract(PlayerInteractEvent event) {
        PlayerInteractEvent.Action action = event.getAction();
        if (action == PlayerInteractEvent.Action.RIGHT_CLICK_AIR) {
            onInteractAir(event);
            return;
        }
        if (action != PlayerInteractEvent.Action.RIGHT_CLICK_BLOCK) {
            return;
        }
        Player player = event.getPlayer();
        Block clicked = event.getBlock();
        boolean isTableBlock = clicked instanceof UnoTableBlocks.UnoTableBlock;
        UnoTable table = isTableBlock
                ? findTable(player.getLevel(),
                        clicked.getFloorX(), clicked.getFloorY(), clicked.getFloorZ())
                : null;

        // 「蹲下 + 手持定位器」：这次使用键优先当**激光开关**（点到哪儿都行）——
        // 但只要准星真的点到牌 / 按钮（= 触发了棋盘的交互），出牌逻辑优先，开关不生效。
        if (laserMode(player)) {
            event.setCancelled(true);
            if (!claimClick(player)) {
                // 同一次点击的另一路事件（方块 + 空中 + 实体三路都会来），吞掉即可
                return;
            }
            if (table != null && table.useBoard(player, false)) {
                return;
            }
            toggleLaser(player);
            return;
        }

        if (isTableBlock) {
            event.setCancelled(true);
            if (table != null && claimClick(player)) {
                table.useBoard(player);
            }
            return;
        }
        if (event.getItem() instanceof UnoTableItem) {
            if (event.isCancelled() || !canPlace(player)) {
                event.setCancelled(true);
                return;
            }
            tryPlace(player, event);
        }
    }

    /**
     * 同一次右键只处理一遍。
     * <p>
     * 一次右键可能同时派发好几条事件 —— 「右键方块」+「右键空中」+「命中实体」，
     * 而**手持定位器**时客户端还会额外发一条「使用物品」事务（MOT 的
     * {@code UseItemProcessor_v113} 收到后会再派发一条 {@code RIGHT_CLICK_AIR}）。
     * 若都放行，同一次点击会被当成两次：先选中某张牌、紧接着又被"再点一次"取消，
     * 表现就是「点了没反应」。
     *
     * @return true = 这次右键还没被处理过（调用方可以继续处理）
     */
    private boolean claimClick(Player player) {
        int now = Server.getInstance().getTick();
        Integer last = clickTicks.get(player.getUniqueId());
        if (last != null && last == now) {
            return false;
        }
        clickTicks.put(player.getUniqueId(), now);
        return true;
    }

    /**
     * 右键空中：准星落在方块之外，但玩家可能正瞄着悬空的手牌 / 桌面按钮。
     * <p>
     * 只在「已入座 + 就在自己那张桌子旁边 + 射线真的命中了手牌或按钮」时才处理并吞掉事件。
     * 三个条件缺一不可：没入座的人看桌面按钮也没意义（按钮只对行动方可见），
     * 未命中则什么都不做 —— 空中右键平时（吃东西、用道具、别的插件的物品）有自己的语义，不能乱拦。
     * <p>
     * 例外：**蹲下 + 手持定位器**时使用键是有语义的 —— 未命中棋盘元素就切激光开关（见 toggleLaser），
     * 无论人在不在牌桌旁（手持物品的「使用」事务在哪儿都会被客户端发出来）。
     */
    private void onInteractAir(PlayerInteractEvent event) {
        Player player = event.getPlayer();
        UnoTable table = seatings.get(player.getUniqueId());
        boolean laser = laserMode(player);

        if (table == null || !table.inUseRange(player)) {
            if (laser && claimClick(player)) {
                event.setCancelled(true);
                toggleLaser(player);
            }
            return;
        }
        // 同一次右键可能派发多条事件（见 claimClick：手持定位器时「方块 + 空中 + 实体」
        // 三路都会来），只认第一条，否则会「选中 → 立刻取消选中」，看起来完全没反应。
        if (!claimClick(player)) {
            return;
        }
        if (table.useBoardAir(player)) {
            event.setCancelled(true);
            return;
        }
        if (laser) {
            event.setCancelled(true);
            toggleLaser(player);
        }
    }

    /** 放置冷却去重：一次点击可能派发多个交互事件。 */
    private boolean canPlace(Player player) {
        long now = System.currentTimeMillis();
        Long last = placeCooldown.get(player.getUniqueId());
        if (last != null && now - last < PLACE_COOLDOWN_MS) {
            return false;
        }
        placeCooldown.put(player.getUniqueId(), now);
        return true;
    }

    /** 铺设 3x3 牌桌（区域以点击方块的对侧邻格为中心回退 1 格）。 */
    private void tryPlace(Player player, PlayerInteractEvent event) {
        BlockFace face = event.getFace();
        if (face == null) {
            return;
        }
        Vector3 target = event.getBlock().getSide(face);
        int bx = target.getFloorX() - 1;
        int by = target.getFloorY();
        int bz = target.getFloorZ() - 1;
        Level level = player.getLevel();

        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 3; j++) {
                Block b = level.getBlock(bx + i, by, bz + j);
                if (!b.isAir() && !b.canBeReplaced()) {
                    player.sendTip("§c空间不足，铺设牌桌需要 3x3 空地。");
                    return;
                }
            }
        }
        for (UnoTable t : tables.values()) {
            if (t.getLevel() != level || t.getBaseY() != by) {
                continue;
            }
            if (bx < t.getBaseX() + 3 && t.getBaseX() < bx + 3
                    && bz < t.getBaseZ() + 3 && t.getBaseZ() < bz + 3) {
                player.sendTip("§c这里已经有牌桌了。");
                return;
            }
        }

        event.setCancelled(true);
        int rotation = (int) Math.round(player.getYaw() / 90.0) & 3;
        placeBlocks(level, bx, by, bz);

        level.addSound(new Vector3(bx + 1.5, by + 0.5, bz + 1.5), Sound.DIG_WOOD, 1.0f, 0.8f);

        UnoTable table = new UnoTable(this, level, bx, by, bz, rotation);
        registerTable(table.getKey(), table);
        markDirty();

        if (!player.isCreative()) {
            Item hand = player.getInventory().getItemInHand();
            if (hand.getCount() <= 1) {
                player.getInventory().setItemInHand(Item.get(Item.AIR));
            } else {
                hand.setCount(hand.getCount() - 1);
                player.getInventory().setItemInHand(hand);
            }
        }
        player.sendTip("§a已铺设 UNO 牌桌，点击牌桌即可打开菜单入座。");
    }

    /**
     * 铺 3x3：中心 1 块 + 边 4 块 + 角 4 块。
     * <p>
     * facing 由几何位置决定（模型零度棱边朝北）：北边=0 西边=1 南边=2 东边=3；
     * 角模型零度棱边为 NE（北+东）→ f 旋转后 NE=0 NW=1 SW=2 SE=3。
     * <b>与资源包 {@code models/blocks/uno/*.geo.json} 的 X 预镜像约定配套</b>，改动必须同步。
     */
    private void placeBlocks(Level level, int bx, int by, int bz) {
        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 3; j++) {
                Vector3 pos = new Vector3(bx + i, by, bz + j);
                if (i == 1 && j == 1) {
                    level.setBlock(pos, new UnoTableBlocks.CenterBlock(), true);
                } else if (i == 1) {
                    UnoTableBlocks.EdgeBlock edge = new UnoTableBlocks.EdgeBlock();
                    edge.setFacing(j == 0 ? 0 : 2);
                    level.setBlock(pos, edge, true);
                } else if (j == 1) {
                    UnoTableBlocks.EdgeBlock edge = new UnoTableBlocks.EdgeBlock();
                    edge.setFacing(i == 0 ? 1 : 3);
                    level.setBlock(pos, edge, true);
                } else {
                    UnoTableBlocks.CornerBlock corner = new UnoTableBlocks.CornerBlock();
                    corner.setFacing(i == 2 ? (j == 0 ? 0 : 3) : (j == 0 ? 1 : 2));
                    level.setBlock(pos, corner, true);
                }
            }
        }
    }

    /** 按坐标命中牌桌（3x3 区域 + 同关卡）。 */
    private UnoTable findTable(Level level, int x, int y, int z) {
        List<UnoTable> list = tablesByLevel.get(level);
        if (list == null) {
            return null;
        }
        for (int i = 0; i < list.size(); i++) {
            UnoTable table = list.get(i);
            if (table.contains(x, y, z)) {
                return table;
            }
        }
        return null;
    }

    /**
     * 牌桌方块可像木板一样被挖掘，但任意一处破坏成功即视作整体收回。
     * {@code ignoreCancelled = true}：出生点保护下事件已取消时不介入，避免整桌被误收。
     */
    @EventHandler(priority = EventPriority.HIGH, ignoreCancelled = true)
    public void onBreak(BlockBreakEvent event) {
        Block block = event.getBlock();
        if (!(block instanceof UnoTableBlocks.UnoTableBlock)) {
            return;
        }
        event.setCancelled(true);
        Level level = block.getLevel();
        level.addSound(
                new Vector3(block.getFloorX() + 0.5, block.getFloorY() + 0.5, block.getFloorZ() + 0.5),
                Sound.DIG_WOOD, 1.0f, 1.0f);
        UnoTable table = findTable(level, block.getFloorX(), block.getFloorY(), block.getFloorZ());
        if (table == null) {
            return;
        }
        retract(event.getPlayer(), table,
                new Vector3(block.getFloorX() + 0.5, block.getFloorY() + 0.25, block.getFloorZ() + 0.5));
    }

    /** 整体收回牌桌：延迟一 tick 回收实体与方块，并按需掉落牌桌物品。 */
    private void retract(Player player, UnoTable table, Vector3 dropAt) {
        boolean drop = !player.isCreative();
        Level level = table.getLevel();
        Server.getInstance().getScheduler().scheduleDelayedTask(plugin, () -> {
            if (!tables.containsKey(table.getKey())) {
                return;
            }
            table.destroy();
            markDirty();
            if (drop) {
                level.dropItem(dropAt, new UnoTableItem());
            }
        }, 1);
    }

    /**
     * 右键命中牌桌实体时：吞掉事件并把准星交给牌桌做射线判定。
     * <p>
     * <b>现状（2026-10-15）</b>：牌桌实体与「隐形载体」的碰撞箱都是默认 0.001
     * （用户要求把捕获框**恢复原样**），准星实际不会再命中它们 —— 悬空手牌的点击
     * 由「定位器」持握道具承担（手持物品的"使用"事务一定会上报服务端）。
     * 这里保留分派逻辑：日后若有实体重新带上真实碰撞箱，右键仍会走同一条
     * {@link UnoTable#useBoard(cn.nukkit.Player)} 路径（命中手牌/按钮就操作，没命中就开菜单）。
     * 蹲下 + 手持定位器时例外，见下面的激光开关分支。
     */
    @EventHandler(priority = EventPriority.HIGH)
    public void onInteractEntity(PlayerInteractEntityEvent event) {
        Player player = event.getPlayer();
        UnoTable table = null;
        if (event.getEntity() instanceof UnoTableEntity entity) {
            table = entity.getTable();
        } else if (event.getEntity() instanceof UnoClickBoxEntity box) {
            table = box.getTable();
        }
        boolean laser = laserMode(player);
        if (table == null) {
            // 不是牌桌实体：激光模式下这次「使用」直接当开关（并吞掉，免得顺带触发了别的交互）
            if (laser && claimClick(player)) {
                event.setCancelled(true);
                toggleLaser(player);
            }
            return;
        }
        event.setCancelled(true);
        if (!claimClick(player)) {
            return;
        }
        if (laser) {
            // 蹲下：点到牌 / 按钮照常走棋盘（出牌、按按钮）；什么都没命中 → 切激光开关，且不弹菜单
            if (!table.useBoard(player, false)) {
                toggleLaser(player);
            }
        } else {
            table.useBoard(player);
        }
    }

    // ------------------------------------------------------------------
    // 存档
    // ------------------------------------------------------------------

    /**
     * 一条牌桌记录。
     * <p>
     * 只持久化「摆放位置 + 朝向 + 倍数 k」：玩家座位是瞬时状态，重启后一律回到待入座；
     * UNO 的对局状态（108 个卡槽分布 + 回合）体量大且无法在无人时续玩，不做持久化。
     */
    private static Map<String, Object> toMap(UnoTable table) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("world", table.getLevel().getName());
        m.put("x", table.getBaseX());
        m.put("y", table.getBaseY());
        m.put("z", table.getBaseZ());
        m.put("rotation", table.getRotation());
        m.put("coefficient", table.getCoefficient());
        return m;
    }

    private File storageFile() {
        return BoardStorage.file(plugin, STORAGE_FILE);
    }

    private void save() {
        if (!restored || saveExecutor.isShutdown()) {
            return;
        }
        File file = storageFile();
        saveExecutor.execute(() -> writeYaml(file, collect()));
    }

    /** 关服兜底：同步排队写盘并等待队列中已有的写入全部完成。 */
    public void saveNow() {
        if (!restored) {
            return;
        }
        File file = storageFile();
        Object data = collect();
        if (saveExecutor.isShutdown()) {
            writeYaml(file, data);
            return;
        }
        saveExecutor.execute(() -> writeYaml(file, data));
        saveExecutor.shutdown();
        try {
            if (!saveExecutor.awaitTermination(5, TimeUnit.SECONDS)) {
                plugin.getLogger().warning("等待 UNO 牌桌数据写入超时。");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private Map<String, Object> collect() {
        List<Map<String, Object>> data = new ArrayList<>(tables.size());
        for (UnoTable table : tables.values()) {
            data.add(toMap(table));
        }
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("tables", data);
        return root;
    }

    private void writeYaml(File file, Object data) {
        try {
            Files.writeString(file.toPath(), BoardStorage.dump(data), StandardCharsets.UTF_8);
        } catch (IOException e) {
            plugin.getLogger().warning("保存 UNO 牌桌数据失败：" + e.getMessage());
        }
    }

    /** 请求在关卡加载完成后恢复磁盘上的牌桌。 */
    public void requestLoad() {
        this.loadPending = true;
    }

    /**
     * 从磁盘恢复牌桌：读文件与解析在异步线程，重建方块与实体回主线程。
     * <p>加载完成前 {@code restored} 保持 false，写盘会被跳过，避免用空数据覆盖存档。
     */
    public void load() {
        File file = storageFile();
        Server.getInstance().getScheduler().scheduleTask(plugin, () -> {
            List<Map<?, ?>> saved = parse(file);
            Server.getInstance().getScheduler().scheduleTask(plugin, () -> {
                for (Map<?, ?> record : saved) {
                    restoreTable(record);
                }
                restored = true;
                if (!saved.isEmpty()) {
                    plugin.getLogger().info("已从磁盘恢复 " + tables.size() + " 张 UNO 牌桌。");
                }
            }, false);
        }, true);
    }

    /** 读取并解析存档（不触碰世界，可在异步线程执行）。 */
    private List<Map<?, ?>> parse(File file) {
        List<Map<?, ?>> saved = new ArrayList<>();
        if (!file.isFile()) {
            return saved;
        }
        Object data = BoardStorage.load(file);
        if (!(data instanceof Map<?, ?> root) || !(root.get("tables") instanceof List<?> list)) {
            if (data == null) {
                plugin.getLogger().warning("读取 UNO 牌桌数据失败（YAML 解析失败或文件不可读）："
                        + file.getName());
            }
            return saved;
        }
        for (Object item : list) {
            if (item instanceof Map<?, ?> record) {
                saved.add(record);
            }
        }
        return saved;
    }

    private void restoreTable(Map<?, ?> record) {
        String world = BoardStorage.stringValue(record, "world", "");
        Level level = Server.getInstance().getLevelByName(world);
        if (level == null) {
            plugin.getLogger().warning("UNO 牌桌所在世界未加载，跳过：" + world);
            return;
        }
        int x = BoardStorage.intValue(record, "x", 0);
        int y = BoardStorage.intValue(record, "y", 0);
        int z = BoardStorage.intValue(record, "z", 0);
        int rotation = BoardStorage.intValue(record, "rotation", 0);
        // 自定义方块 id 重启后可能重新分配，这里按坐标重放一遍，确保牌桌方块仍然有效
        placeBlocks(level, x, y, z);
        UnoTable table = new UnoTable(this, level, x, y, z, rotation);
        table.restoreCoefficient(BoardStorage.doubleValue(record, "coefficient", 0.0));
        registerTable(table.getKey(), table);
    }
}
