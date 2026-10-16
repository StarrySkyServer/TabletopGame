package com.tabletopgame.game;

import cn.nukkit.Player;
import cn.nukkit.Server;
import cn.nukkit.block.Block;
import cn.nukkit.entity.Entity;
import cn.nukkit.event.player.PlayerTeleportEvent;
import cn.nukkit.level.Level;
import cn.nukkit.level.Location;
import cn.nukkit.level.Position;
import cn.nukkit.math.Vector3;
import cn.nukkit.network.protocol.AnimateEntityPacket;
import com.tabletopgame.economy.EconomyHook;
import com.tabletopgame.ai.UnoAi;
import com.tabletopgame.board.UnoTableBlocks;
import com.tabletopgame.entity.UnoClickBoxEntity;
import com.tabletopgame.entity.UnoTableEntity;
import com.tabletopgame.entity.UnoTableEntity.Controls;
import com.tabletopgame.item.LocatorItem;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Locale;
import java.util.Random;
import java.util.UUID;

/**
 * 一张已放置的 UNO 牌桌（3x3 物理牌桌 + 单个渲染实体）。
 *
 * <h2>渲染</h2>
 * 整桌状态由 {@link UnoTableEntity} 的 <b>26 个整型属性</b>同步给客户端，客户端
 * {@code pre_animation} 解码后由 {@code animation.tabletopgame.uno.layout} 驱动 390 根骨骼；
 * 选牌 / 按钮通过 {@link UnoTableRay} 对玩家视线做射线拾取（与斗地主同一套已实测的数学）。
 * 与斗地主的差别：<b>没有激光笔</b>，右键牌桌即按准星命中直接交互。
 *
 * <h2>节拍</h2>
 * 管理器每 5 游戏 tick 调一次 {@link #tick()}（每秒 4 次）：
 * <ul>
 *   <li>{@code WAITING}：等待入座 / 点「开始游戏」（≥2 座位占用即可）；</li>
 *   <li>{@code DEALER_DRAW}：<b>自动</b>四家同时各抽一张比大小定庄，一张消息一起播报，
 *       四张牌各摆在自己那侧出牌区展示 2 秒后消失并开始发牌；</li>
 *   <li>{@code PLAYING}：人来点世界内按钮，机器人 / 离线托管按延迟自动行动；</li>
 *   <li>{@code SETTLED}：展示 20 秒，期间可点「下一局 / 退出」，超时退回 WAITING 保留座位。</li>
 * </ul>
 *
 * <h2>座位与局内编号</h2>
 * 牌桌座位 0..3 = <b>东(南)西(北) = P1..P4</b>，已按顺时针排列（与 {@code OUT_X/OUT_Z}、
 * 动画 {@code SEAT_YAW} 一致），玩家可自选座位。而 {@link UnoGame} 只认 0..n-1 的连续编号，
 * 因此开局时按<b>座位升序</b>建立双向映射 {@link #gameOfSeat}/{@link #seatOfGame}：
 * 升序即顺时针序，保证「顺时针轮转」在自由选座下依然成立（如占 {0,2,3} → 局内 0↔座0、1↔座2、2↔座3）。
 *
 * <h2>手牌槽与卡槽</h2>
 * 实体属性里每张牌占一个<b>卡槽 = 牌 id</b>（0..107）。客户端 pre_animation 扫描卡槽升序
 * 统计每个区（座位）内的序号，因此<b>展示顺序恒为卡槽升序</b>；{@link UnoDeck#sortHand}
 * 的排序键（色 → 牌型 → 数字）恰好等价于牌 id 升序，两者天然一致 —— 即
 * 「手牌列表第 i 张」就是「区内第 i 张」，射线与选中/高亮值都以牌 id 直接编码，无需换算序号。
 *
 * <h2>经济</h2>
 * 开局不动账；结算按官方记分「Σ(其余各家剩余手牌分) × k」，<b>k 由第一个入座者设定</b>（默认 1），
 * 赢家实得扣除官方抽水后的部分。机器人不参与金钱往来（否则人机局等于无风险刷币）。
 */
public class UnoTable {

    /** 「能点到这张桌子」的距离上限（方块，玩家到桌心的水平距离）；基岩交互距离约 5.5。 */
    private static final double USE_RANGE = 6.0;

    /** 管理器每 5 游戏 tick 调一次本表 tick → 每秒 4 次。 */
    public static final int TICKS_PER_SECOND = 4;

    /** 结算展示时长（20 秒）；期间无人点「下一局」则退回 WAITING（保留座位）。 */
    private static final int SETTLE_INTERVAL = 20 * TICKS_PER_SECOND;

    /** 定庄阶段每张牌的间隔（0.5 秒）。 */
    private static final int DEALER_DRAW_DELAY = 2;
    /** 定庄比大小的牌展示时长（2 秒 = 8 表 tick）。 */
    private static final int DEALER_SHOW_TICKS = 8;
    /** 机器人 / 托管思考固定 2 秒（8 表 tick），让出牌节奏更像真人。 */
    private static final int BOT_THINK_TICKS = 8;
    /** 人类回合超时（45 秒）：自动「摸牌 → 不出」，避免离席卡死全桌。 */
    private static final int HUMAN_TURN_TIMEOUT = 45 * TICKS_PER_SECOND;

    /** 视角动画刷新间隔（表 tick）。 */
    private static final int VIEWER_REFRESH = 20;
    /** 准星高亮刷新间隔（表 tick）。 */
    private static final int HOVER_INTERVAL = 2;
    /** 旁观者隐藏牌面的广播半径（方块）。 */
    private static final double SPECTATOR_RANGE = 16.0;

    /** 倍数 k 上限（整数）。0 表示免费局。 */
    public static final double MAX_COEFFICIENT = 1000.0;

    /** UNO 喊声（资源包 sound_definitions 中的 {@code tabletopgame.uno.call}）。 */
    private static final String SND_UNO_CALL = "tabletopgame.uno.call";

    /** 空按钮组。 */
    private static final int[] EMPTY_BUTTONS = new int[0];
    /** 空手牌。 */
    private static final int[] EMPTY_HAND = new int[0];

    /** 座位中文名，索引即座位号（0=东 1=南 2=西 3=北）。 */
    private static final String[] SEAT_LABEL = {"东（P1）", "南（P2）", "西（P3）", "北（P4）"};

    // ---------------- 入座归位（传送到站位 + 转向棋心）----------------

    /** 站位半径：座位棋心向桌外退 3.0 格（棋盘外隔 1 格，看得全又不挡牌）。 */
    private static final double SEAT_STAND_RADIUS = 3.0;
    /** 站位视线俯角：看向高度 ≈ 桌心上方 0.6 格（牌面区域中心）。 */
    private static final double SEAT_FACE_TARGET_Y = 0.6;
    /** 站位被方块挡住时向上找空位的最大格数。 */
    private static final int SEAT_SEEK_UP = 3;

    /** 隐形载体（点击箱 / 倒计时牌）生成时的抬升：略高于桌面顶面，避免与桌体穿模。 */
    private static final double CLICK_BOX_LIFT = 0.3;
    /** 悬浮倒计时牌子在桌面上方的抬升（真实视角反推 0.62 格）。 */
    private static final double COUNTDOWN_LIFT = 0.62;

    /** 牌桌级阶段。 */
    public enum TablePhase {
        /** 等待入座 / 点开始。 */
        WAITING,
        /** 抽牌比大小定庄（自动）。 */
        DEALER_DRAW,
        /** 对局进行中。 */
        PLAYING,
        /** 结算展示中。 */
        SETTLED
    }

    private final UnoManager manager;
    private final Level level;
    private final int baseX;
    private final int baseY;
    private final int baseZ;
    private final int rotation;
    private final String key;
    private final Random random = new Random();

    /** 3x3 中心（世界坐标）。 */
    private final Vector3 center;
    /** 渲染实体原点：桌面顶面（15/16）中心，射线与局部坐标基准。 */
    private final Vector3 origin;

    private UnoTableEntity visual;
    /** 隐形载体实体（碰撞箱已恢复默认 0.001，不再捕获准星），见 {@link #spawnClickBox()}。 */
    private UnoClickBoxEntity clickBox;

    /** 悬浮倒计时的牌子（同类空实体，只显示 name tag），见 {@link #setCountdownText(String)}。 */
    private UnoClickBoxEntity countdown;

    /** 当前挂在牌子上的文字（null = 不显示）；内容没变就不重复发包。 */
    private String countdownText;

    /** 结算展示板：0 = 桌心标题，1..4 = 各座位明细（出牌区上方）；null = 未显示。 */
    private final UnoClickBoxEntity[] settleBoard = new UnoClickBoxEntity[5];
    /** 结算板当前文字（内容没变就不重复发包）。 */
    private final String[] settleText = new String[5];
    /** 经济结算快照：每座位实扣额（免费局 / 机器人胜 = 全 0），见 {@link #settleEconomy()}。 */
    private final double[] settlePaid = new double[4];
    /** 经济结算快照：赢家税后实得（免费局 = 0）。 */
    private double settlePrize;

    // ---------------- 座位 ----------------
    /** 每座位人类成员 UUID（null = 空位或机器人）。 */
    private final UUID[] humans = new UUID[4];
    /** 每座位在线玩家（null = 离线或机器人）。 */
    private final Player[] online = new Player[4];
    /** 每座位机器人档位（{@link UnoAi#LEVEL_EASY}..{@link UnoAi#LEVEL_MASTER}；-1 = 不是机器人）。 */
    private final int[] bots = {-1, -1, -1, -1};
    /** 每座位显示名（离线后仍可播报）。 */
    private final String[] names = new String[4];
    /** 第一个入座的人类（负责设定倍数 k）。 */
    private UUID firstJoiner;

    // ---------------- 对局状态 ----------------
    private TablePhase phase = TablePhase.WAITING;
    private UnoGame game;
    /** 局内编号（0..gamePlayers-1）→ 牌桌座位。 */
    private final int[] seatOfGame = new int[4];
    /** 牌桌座位 → 局内编号；-1 = 未参与本局。 */
    private final int[] gameOfSeat = {-1, -1, -1, -1};
    private int gamePlayers;

    /** 每座位已选中的牌 id（-1 = 未选中）。 */
    private final int[] selected = {-1, -1, -1, -1};
    /**
     * 每座位「选中已锁定」（摸牌后强制选中摸到的那张，直到出牌或跳过才解锁）。
     * <p>
     * 需求原话：「这个牌不能收回，只能等你选择出牌或者跳过之后，这个牌才正常地收回不突出。
     * 然后这时候应该不能碰其他的来控它的突出和不突出。」因此锁定期间点别的手牌不改选中。
     */
    private final boolean[] selectLocked = {false, false, false, false};
    /** 每座位「已打出野牌、等待选色」的牌 id（-1 = 无）。 */
    private final int[] pendingWild = {-1, -1, -1, -1};
    /** 每座位准星值。 */
    private final int[] hover = new int[4];
    /** 每座位「提示」循环下标。 */
    private final int[] hintIndex = new int[4];

    /**
     * 每座位是否「托管」：玩家本人还在座（{@link #humans} / {@link #online} 都有效），
     * 但把出牌权交给系统代打（菜单里的「托管（系统代打）」按钮切换）。
     * <p>
     * 与「机器人」（{@link #bots}，占的是空位）和「离线托管」（{@code online == null}）区分开：
     * 三者在客户端都用同一个机器人模型表示，见 {@link #seatsState()}。
     */
    private final boolean[] trusted = {false, false, false, false};

    /** 0 人入座时的菜单持有者与到期时间。 */
    private UUID menuHolder;
    private long menuHolderUntil;

    /** 每分倍数 k（由第一入座者设定）。默认 <b>0 = 免费局</b>：不扣钱、不抽水。 */
    private double coefficient = 0.0;

    private int tableTick;
    private int hoverTick;
    private int viewerTick;
    private int settleTicks;
    private int actionTicks;
    private int actionLimit;
    private int dealerIdx;
    /**
     * 定庄子状态：0 = 还没抽牌；1 = 比大小展示中（{@link #dealerShowTicks} 倒计时）；
     * 2 = 庄家已定（本 tick 已发牌开局）。
     */
    private int dealerStep;
    /** 展示倒计时（表 tick）。 */
    private int dealerShowTicks;
    /** 本轮比大小是否并列（1 = 并列，展示满 2 秒后重抽）。 */
    private int dealerTie;
    private int roundNumber;

    /**
     * 逐张发牌进度：每个座位区内已亮出的张数；{@link UnoTableEntity#DEAL_DONE} = 已完成。
     * <p>
     * 需求「复刻斗地主那种牌一张张出来，而不是一下子出来」：发牌本身是瞬时的（服务端一次
     * {@code deal()}），但客户端只在 {@code v.sN < uno_deal} 时显示第 N 张 —— 服务端逐 tick
     * 递增这个值，四家的第 k 张同时亮出，观感与真实发牌一致（一圈一张）。
     */
    private int dealShown = UnoTableEntity.DEAL_DONE;

    /**
     * 出牌飞行序号：每触发一次就把 bit1 取反（客户端只认「{@code uno_fly} 值变了」）。
     * 翻转位保证相邻两次出牌写入的值一定不同 —— 写同一个值客户端认不出新的一次。
     */
    private int flySeq;

    /** 本 tick 同步给客户端的 {@code uno_fly} 值：bit0 = 来源（0 手牌 / 1 牌堆），bit1 = 翻转位。 */
    private int flyValue;
    /** 本轮发牌需要亮到多少张（= 开局手牌张数）。 */
    private int dealTarget;
    /** 距离下一张亮出的表 tick 计数。 */
    private int dealTick;
    /** 每张牌之间的间隔（表 tick；1 表 tick ≈ 50ms）。 */
    private static final int DEAL_INTERVAL = 3;
    /** {@link #tickDealing} 里每 tick 累加的步长（2 = 每 1.5 表 tick 亮一张，发牌耗时减半）。 */
    private static final int DEAL_STEP = 2;
    private int lastKey = -1;
    private boolean settledFlag;
    /** 连续「行动未推进状态」的计数（自愈兜底用）。 */
    private int stallCount;

    /** 有属性 / 状态变化待同步（tick 末尾统一发包）。 */
    private boolean dirty = true;

    public UnoTable(UnoManager manager, Level level,
                    int baseX, int baseY, int baseZ, int rotation) {
        this.manager = manager;
        this.level = level;
        this.baseX = baseX;
        this.baseY = baseY;
        this.baseZ = baseZ;
        this.rotation = rotation;
        this.key = level.getName() + ":" + baseX + ":" + baseY + ":" + baseZ;
        this.center = new Vector3(baseX + 1.5, baseY + 0.5, baseZ + 1.5);
        this.origin = new Vector3(baseX + 1.5, baseY + 15.0 / 16.0, baseZ + 1.5);
        spawnEntity();
    }

    // ==================================================================
    // 基本访问
    // ==================================================================

    public String getKey() {
        return key;
    }

    public Level getLevel() {
        return level;
    }

    public Vector3 getCenter() {
        return center;
    }

    public Vector3 getOrigin() {
        return origin;
    }

    public int getBaseX() {
        return baseX;
    }

    public int getBaseY() {
        return baseY;
    }

    public int getBaseZ() {
        return baseZ;
    }

    public int getRotation() {
        return rotation;
    }

    public TablePhase getPhase() {
        return phase;
    }

    public int getRoundNumber() {
        return roundNumber;
    }

    public double getCoefficient() {
        return coefficient;
    }

    /** 座位中文名（0=东 1=南 2=西 3=北）。 */
    public static String seatLabel(int seat) {
        return seat >= 0 && seat < 4 ? SEAT_LABEL[seat] : "—";
    }

    /** 该坐标是否属于本牌桌（3x3 区域）。 */
    public boolean contains(int x, int y, int z) {
        return x >= baseX && x < baseX + 3
                && z >= baseZ && z < baseZ + 3
                && y == baseY;
    }

    public boolean inRange(Player player) {
        if (player.getLevel() != this.level) {
            return false;
        }
        double range = manager.playerRange();
        return Math.abs(player.x - center.x) <= range
                && Math.abs(player.z - center.z) <= range
                && Math.abs(player.y - center.y) <= 12.0;
    }

    /**
     * 玩家是否近到「能点到这张桌子」：用于右键空中时挑选目标牌桌。
     * <p>
     * 与 {@link #inRange} 的区别：那个是「能看到桌上信息」的展示半径（配置项，可能很大），
     * 这个是基岩的交互距离（约 5.5 格）留一点余量，避免隔着半条街右键空中就误判成点桌子。
     */
    public boolean inUseRange(Player player) {
        if (player.getLevel() != this.level) {
            return false;
        }
        double dx = player.x - center.x;
        double dz = player.z - center.z;
        return dx * dx + dz * dz <= USE_RANGE * USE_RANGE
                && Math.abs(player.y - center.y) <= 8.0;
    }

    /** 座位是否被占用（人类或机器人）。 */
    public boolean isOccupied(int seat) {
        return humans[seat] != null || bots[seat] >= 0;
    }

    public int occupiedSeats() {
        int n = 0;
        for (int s = 0; s < 4; s++) {
            if (isOccupied(s)) {
                n++;
            }
        }
        return n;
    }

    public boolean isBot(int seat) {
        return bots[seat] >= 0;
    }

    /** 玩家所在座位；-1 = 不在座。 */
    public int seatOf(UUID id) {
        if (id == null) {
            return -1;
        }
        for (int s = 0; s < 4; s++) {
            if (id.equals(humans[s])) {
                return s;
            }
        }
        return -1;
    }

    public boolean isSeated(UUID id) {
        return seatOf(id) >= 0;
    }

    /** 是否本桌成员（含机器人占位的座位号）。 */
    public List<Integer> occupiedSeatList() {
        List<Integer> out = new ArrayList<>(4);
        for (int s = 0; s < 4; s++) {
            if (isOccupied(s)) {
                out.add(s);
            }
        }
        return out;
    }

    /** 座位显示名。 */
    public String seatName(int seat) {
        if (names[seat] != null) {
            return names[seat];
        }
        return "座位" + (seat + 1);
    }

    /** 该座位当前的在线玩家（null = 离线 / 空位 / 机器人）。 */
    public Player onlineAt(int seat) {
        return seat >= 0 && seat < 4 ? online[seat] : null;
    }

    /** 「0 人入座」菜单持有者（可能尚未入座）。 */
    public UUID menuHolderId() {
        return menuHolder;
    }

    /** 是否为第一个入座者（负责设定倍数 k）。 */
    public boolean isFirstJoiner(UUID id) {
        return firstJoiner != null && firstJoiner.equals(id);
    }

    /** 是否已有一个「机器人」占位（供菜单显示「清除人机」）。 */
    public boolean hasBots() {
        for (int s = 0; s < 4; s++) {
            if (bots[s] >= 0) {
                return true;
            }
        }
        return false;
    }

    private static String fmt(double v) {
        // k 现在是整数，金额基本也是整数：整数就不显示 ".00"，看起来清爽
        if (v == Math.rint(v) && Math.abs(v) < 1.0E15) {
            return String.format(Locale.ROOT, "%,d", (long) Math.rint(v));
        }
        return String.format(Locale.ROOT, "%,.2f", v);
    }

    // ==================================================================
    // 菜单占用（0 人入座时独占）
    // ==================================================================

    /** 0 人入座时抢占菜单；已有人入座则永远返回 true。 */
    public boolean tryAcquireMenu(Player player) {
        if (occupiedSeats() > 0) {
            return true;
        }
        long now = System.currentTimeMillis();
        UUID id = player.getUniqueId();
        if (menuHolder != null && !menuHolder.equals(id) && now < menuHolderUntil) {
            return false;
        }
        menuHolder = id;
        menuHolderUntil = now + manager.menuLockMs();
        return true;
    }

    public void releaseMenu(UUID id) {
        if (menuHolder != null && menuHolder.equals(id)) {
            menuHolder = null;
        }
    }

    public void releaseMenu(Player player) {
        releaseMenu(player.getUniqueId());
    }

    /** 是否仍持有「0 人入座」菜单占用权（持有即在用并续期）。 */
    public boolean holdsMenu(Player player) {
        if (occupiedSeats() > 0) {
            return true;
        }
        long now = System.currentTimeMillis();
        UUID id = player.getUniqueId();
        if (menuHolder == null || !menuHolder.equals(id) || now >= menuHolderUntil) {
            return false;
        }
        menuHolderUntil = now + manager.menuLockMs();
        return true;
    }

    /** 菜单占用兜底清理：持有者超时或下线时关闭其表单并释放占用。 */
    public void tickMenuHolder() {
        if (menuHolder == null) {
            return;
        }
        if (occupiedSeats() > 0) {
            menuHolder = null;
            return;
        }
        Player holder = Server.getInstance().getPlayer(menuHolder).orElse(null);
        if (holder == null) {
            menuHolder = null;
            return;
        }
        if (System.currentTimeMillis() < menuHolderUntil) {
            return;
        }
        holder.closeFormWindows();
        holder.sendTip("§e菜单操作超时，已自动关闭。");
        menuHolder = null;
    }

    // ==================================================================
    // 实体生成 / 销毁
    // ==================================================================

    private void spawnEntity() {
        Entity e = Entity.createEntity(UnoTableEntity.IDENTIFIER, Position.fromObject(origin, level));
        if (e instanceof UnoTableEntity t) {
            visual = t;
            t.setTable(this);
            t.spawnToAll();
            dirty = true;
        }
        spawnClickBox();
    }

    /**
     * 生成「隐形载体」实例（与倒计时牌子同族）：不渲染、碰撞箱保持默认 0.001。
     * <p>
     * 它以前是「点击捕获框」（碰撞箱放大到 3×1.9×3，让准星在悬空手牌上也能命中"某个实体"），
     * 2026-10-15 用户要求**恢复原样**：准星交互现由「定位器」道具承担（手持物品的
     * "使用"事务一定会上报服务端），这里不再放大箱子 —— 对客户端而言它等同于不存在。
     */
    private void spawnClickBox() {
        Entity h = Entity.createEntity(UnoClickBoxEntity.IDENTIFIER,
                Position.fromObject(new Vector3(origin.x, origin.y + CLICK_BOX_LIFT, origin.z), level));
        if (h instanceof UnoClickBoxEntity b) {
            clickBox = b;
            b.setTable(this);
            b.spawnToAll();
        }
        spawnCountdown();
    }

    /**
     * 生成「悬浮倒计时」牌子：同一族空实体的第二个实例，摆在牌桌正上方
     * {@link #COUNTDOWN_LIFT} 格处，**不画模型**，只靠 name tag 显示文字
     * —— 也就是「固定在方块上方的悬浮窗」（需求原话）。
     */
    private void spawnCountdown() {
        Entity e = Entity.createEntity(UnoClickBoxEntity.IDENTIFIER,
                Position.fromObject(new Vector3(origin.x, origin.y + COUNTDOWN_LIFT, origin.z), level));
        if (e instanceof UnoClickBoxEntity c) {
            countdown = c;
            c.setTable(this);
            c.setFloatingText(null);        // 初始不显示
            c.spawnToAll();
        }
    }

    /** 区块重载后按需重建实体（实体 {@code setCanBeSavedWithChunk(false)}）。 */
    private void ensureEntities() {
        boolean needVisual = visual == null || visual.isClosed();
        boolean needBox = clickBox == null || clickBox.isClosed();
        boolean needCountdown = countdown == null || countdown.isClosed();
        if (!needVisual && !needBox && !needCountdown) {
            return;
        }
        if (!level.isChunkLoaded((baseX + 1) >> 4, (baseZ + 1) >> 4)) {
            return;
        }
        if (needVisual) {
            spawnEntity();
        } else if (needBox || needCountdown) {
            spawnClickBox();
        }
        refreshViewers();
        dirty = true;
    }

    /** 销毁牌桌：实体、9 个方块、座位与注册全部回收。 */
    public void destroy() {
        for (int s = 0; s < 4; s++) {
            if (humans[s] != null) {
                manager.unseat(humans[s]);
            }
            // 牌桌被拆了 → 把在座玩家的定位器一并收回，别把道具留在他们背包里
            if (online[s] != null && online[s].isOnline()) {
                manager.takeLocator(online[s]);
            }
        }
        game = null;
        phase = TablePhase.WAITING;
        menuHolder = null;
        if (visual != null && !visual.isClosed()) {
            visual.close();
        }
        visual = null;
        if (clickBox != null && !clickBox.isClosed()) {
            clickBox.close();
        }
        clickBox = null;
        if (countdown != null && !countdown.isClosed()) {
            countdown.close();
        }
        countdown = null;
        countdownText = null;
        closeSettleBoard();
        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 3; j++) {
                Vector3 p = new Vector3(baseX + i, baseY, baseZ + j);
                if (level.getBlock(p) instanceof UnoTableBlocks.UnoTableBlock) {
                    level.setBlock(p, Block.get(Block.AIR), true);
                }
            }
        }
        manager.unregisterTable(key);
    }

    // ==================================================================
    // 主循环
    // ==================================================================

    public void tick() {
        tableTick++;
        ensureEntities();
        if (visual == null || visual.isClosed()) {
            return;
        }
        tickDealing();
        switch (phase) {
            case DEALER_DRAW -> tickDealer();
            case PLAYING -> tickPlaying();
            case SETTLED -> tickSettled();
            default -> {
            }
        }
        // 悬浮倒计时只在「有人正在思考出什么牌」的那段时间挂在牌桌上；其余阶段一律摘掉
        if (phase != TablePhase.PLAYING || dealing()) {
            setCountdownText(null);
        }
        if (++hoverTick >= HOVER_INTERVAL) {
            hoverTick = 0;
            updateHover();
        }
        if (++viewerTick >= VIEWER_REFRESH) {
            viewerTick = 0;
            refreshViewers();
        }
        if (dirty) {
            dirty = false;
            sync();
        }
    }

    // ==================================================================
    // 定庄（自动）
    // ==================================================================

    /**
     * 定庄阶段：四家**同时**各抽一张，同一条消息一起播报，四张牌展示 2 秒后结算。
     * <ul>
     *   <li>抽完立刻 {@link #announceDealerDraw()} 播报（"同时提示"）；</li>
     *   <li>展示期间客户端把四张牌平铺在各自座位的出牌区（{@link UnoTableEntity#SHOW_SHIFT}）；</li>
     *   <li>满 2 秒后：并列 → 全部重抽再来一轮；否则播报庄家并 {@link #startPlay()} 发牌
     *       （发牌前这几张牌就已经从状态里清掉了，不会和发到手里的牌撞脸）。</li>
     * </ul>
     */
    private void tickDealer() {
        if (game == null || game.phase() != UnoGame.PHASE_DEALER_DRAW) {
            return;
        }
        if (dealerStep == 0) {
            int r = game.drawAllForDealer();
            if (r < 0) {
                return;
            }
            announceDealerDraw();
            dealerIdx = gamePlayers;
            dealerTie = r == UnoGame.DRAW_TIE_REDRAW ? 1 : 0;
            dealerStep = 1;
            dealerShowTicks = 0;
            dirty = true;
            return;
        }
        if (dealerStep != 1) {
            return;
        }
        if (++dealerShowTicks < DEALER_SHOW_TICKS) {
            return;
        }
        dealerShowTicks = 0;
        if (dealerTie == 1) {
            broadcast("§e最大点数并列，全部重新抽牌（第 " + game.dealerDrawRound() + " 轮）！");
            dealerStep = 0;
        } else {
            int dealerSeat = seatOfGame[game.dealerSeat()];
            broadcast("§6" + seatName(dealerSeat) + " §7成为庄家，先手为其左手边（顺时针下一位）。");
            dealerStep = 2;
            startPlay();
        }
        dirty = true;
    }

    /** 定庄抽完牌的一条播报：四家的牌 + 比大小点数挤在一行里（需求「同时提示」）。 */
    private void announceDealerDraw() {
        StringBuilder sb = new StringBuilder("§f定庄比大小：");
        for (int g = 0; g < gamePlayers; g++) {
            int seat = seatOfGame[g];
            int card = game.dealerDraw(g);
            sb.append(g > 0 ? " §7| " : " ");
            if (card < 0) {
                sb.append("§8").append(seatName(seat)).append(" ?");
                continue;
            }
            sb.append("§f").append(seatName(seat))
                    .append(" §e").append(UnoDeck.name(card))
                    .append(" §7(").append(UnoGame.dealerPower(card)).append(")");
        }
        broadcast(sb.toString());
    }

    /** 定庄是否正在展示四家的比大小牌（客户端据此把它们摆到各自出牌区）。 */
    private boolean dealerShowing() {
        return phase == TablePhase.DEALER_DRAW && dealerStep == 1;
    }

    /** 定庄完成 → 洗牌发牌 → 进入对局。 */
    private void startPlay() {
        String err = game.deal();
        if (err != null) {
            broadcast("§c发牌失败：" + err);
            resetToWaiting();
            return;
        }
        phase = TablePhase.PLAYING;
        selected[0] = selected[1] = selected[2] = selected[3] = -1;
        pendingWild[0] = pendingWild[1] = pendingWild[2] = pendingWild[3] = -1;
        selectLocked[0] = selectLocked[1] = selectLocked[2] = selectLocked[3] = false;
        lastKey = -1;
        actionTicks = 0;
        actionLimit = computeActionLimit();
        // 逐张发牌：先把所有手牌摆好但隐藏，再逐 tick 亮出（见 tickDealing）
        dealTarget = 0;
        for (int s = 0; s < 4; s++) {
            int g = gameOfSeat[s];
            if (g >= 0) {
                dealTarget = Math.max(dealTarget, game.handSize(g));
            }
        }
        dealShown = dealTarget > 0 ? 0 : UnoTableEntity.DEAL_DONE;
        dealTick = 0;
        int actor = actorSeat();
        if (game.isStartColorPending()) {
            broadcast("§e起始牌是野牌，" + seatName(actor) + " 请先点四种颜色之一。");
        } else {
            broadcast("§a第 " + roundNumber + " 局开始，先出手的是 " + seatName(actor) + "。");
        }
        dirty = true;
    }

    /**
     * 逐张发牌推进（需求「复刻斗地主那种牌一张张出来」）。
     * <p>
     * 发牌期间不解释任何操作：按钮隐藏、操作方视为「不可行动」，避免玩家把还没出现的牌
     * 点掉。发完牌后把思考计时清零，让玩家从「看全手牌」那刻才开始计时。
     */
    private void tickDealing() {
        if (dealShown >= UnoTableEntity.DEAL_DONE) {
            return;
        }
        dealTick += DEAL_STEP;
        if (dealTick < DEAL_INTERVAL) {
            return;
        }
        dealTick = 0;
        dealShown++;
        if (dealShown >= dealTarget) {
            dealShown = UnoTableEntity.DEAL_DONE;
            actionTicks = 0;
            // 发牌一结束，中央那张起始牌就"从牌堆翻出来"飞向庄家面前（见 triggerFlight）
            triggerFlight(true);
        }
        dirty = true;
    }

    /** 是否仍在逐张发牌。 */
    private boolean dealing() {
        return dealShown < UnoTableEntity.DEAL_DONE;
    }

    /**
     * 触发一次「出牌飞行」（客户端自带 0.2 秒，见资源包 build_table 的 FLY_* 说明）。
     * <p>
     * 服务端不做动画 —— 只把 {@code uno_fly} 的**值变一下**（bit1 翻转），客户端检测到变化就把
     * 飞行进度清零、记下起点，然后按 {@code q.delta_time} 自己往前走 0.2 秒：牌从
     * 出牌座位的手牌中心带弧线飞到他的出牌区、同时从 65° 放平（{@code fromPile} 时改成
     * 从中央牌堆顶翻出来、rx 180°→0° 露一圈牌背再翻成牌面）。
     *
     * @param fromPile {@code true} = 从牌堆翻出的起始牌；{@code false} = 正常出牌
     */
    private void triggerFlight(boolean fromPile) {
        flyValue = ((flySeq++ & 1) << 1) | (fromPile ? 1 : 0);
        dirty = true;
    }

    // ==================================================================
    // 出牌 / 摸牌
    // ==================================================================

    /** 当前行动座位（牌桌座位）；无则 -1。 */
    public int actorSeat() {
        if (game == null) {
            return -1;
        }
        if (phase == TablePhase.PLAYING) {
            int g = game.currentSeat();
            return g >= 0 && g < gamePlayers ? seatOfGame[g] : -1;
        }
        // 定庄是四家同时抽，没有「轮到谁」，所以不点回合箭头（旧版是轮流抽才有的）
        return -1;
    }

    /** 该座位现在可否点按钮（结算阶段人人可点「下一局 / 退出」）。 */
    private boolean canAct(int seat) {
        if (seat < 0 || seat > 3) {
            return false;
        }
        if (phase == TablePhase.SETTLED) {
            return humans[seat] != null;
        }
        if (dealing()) {
            // 发牌动画期间不给任何人操作权（也不显示按钮），避免点到还没亮出来的牌
            return false;
        }
        return seat == actorSeat();
    }

    private int stateKey() {
        if (game == null) {
            return -1;
        }
        int actor = actorSeat();
        return (game.currentSeat() & 7)
                | ((game.hasDrawn() ? 1 : 0) << 3)
                | ((game.isStartColorPending() ? 1 : 0) << 4)
                | ((game.phase() == UnoGame.PHASE_FINISHED ? 1 : 0) << 5)
                | ((phase == TablePhase.SETTLED ? 1 : 0) << 6)
                // 进入 / 离开「野牌待选色」也算一次状态变化：否则这段思考会沿用
                // 出牌前的计时计数，玩家还在挑颜色就被判超时代打了。
                | ((actor >= 0 && pendingWild[actor] >= 0 ? 1 : 0) << 7);
    }

    private int computeActionLimit() {
        if (phase == TablePhase.DEALER_DRAW) {
            return DEALER_DRAW_DELAY;
        }
        if (phase != TablePhase.PLAYING) {
            return Integer.MAX_VALUE / 4;
        }
        int actor = actorSeat();
        if (actor < 0) {
            return Integer.MAX_VALUE / 4;
        }
        if (autoPlayed(actor)) {
            return BOT_THINK_TICKS;
        }
        return HUMAN_TURN_TIMEOUT;
    }

    /**
     * 该座位是否由系统代打：机器人占位 / 本人开了托管 / 断线离线。
     * <p>
     * 三种情况共用同一套「机器人节奏」（思考 {@link #BOT_THINK_TICKS} 后自动行动），
     * 差别只在客户端要不要画托管机器人（见 {@link #seatsState()}）。
     */
    private boolean autoPlayed(int seat) {
        return bots[seat] >= 0 || trusted[seat] || online[seat] == null;
    }

    private void tickPlaying() {
        if (dealing()) {
            // 发牌动画没放完不许出牌（需求：机器人也得等发完牌再动，不然牌还在往外发就先出了一手）
            return;
        }
        int actor = actorSeat();
        if (actor < 0) {
            return;
        }
        int key = stateKey();
        if (key != lastKey) {
            lastKey = key;
            actionTicks = 0;
            actionLimit = computeActionLimit();
            stallCount = 0;
        }
        tickCountdown(actor);
        if (++actionTicks < actionLimit) {
            return;
        }
        actionTicks = 0;
        if (autoPlayed(actor)) {
            autoAction(actor, bots[actor] >= 0 ? bots[actor] : UnoAi.LEVEL_NORMAL);
        } else {
            timeoutAction(actor);
        }
        // 兜底：若这一手没能推进状态（理论上不该发生），连续 3 次后强制「摸牌 / 过」，
        // 把「静默卡死全桌」变成「自愈 + 控制台留痕」。
        if (phase == TablePhase.PLAYING && stateKey() == key) {
            if (++stallCount >= 3) {
                stallCount = 0;
                pluginLog("行动未推进状态，强制兜底：seat=" + actor
                        + " actor=" + actorSeat() + " key=" + key);
                forceSafeAction(actor);
            }
        } else {
            stallCount = 0;
        }
    }

    /**
     * 出牌倒计时：把「轮到谁、还剩几秒」写到牌桌正上方的**悬浮牌子**上（世界坐标，固定在方块上方）。
     * <p>
     * 需求出处：用户看到斗地主那边有"出牌倒计时"，问插件能不能做 —— 斗地主那版实现其实
     * **没有**倒计时（Java / 行为包 / 资源包都没有，行为包只有没人调用的 actionbar 工具函数）；
     * 第一版按"屏幕提示"（action bar）做了，用户明确改口：「是那种悬浮窗显示在方块上面，
     * （位置永远固定在方块上），不是屏幕提示，我想用那种」⇒ 改成 name tag 悬浮字。
     * <p>
     * 三条规则不变：
     * <ul>
     *   <li>机器人 / 托管 / 离线座位**不显示**（固定 2 秒就出手，秒级倒计时只会闪）；</li>
     *   <li>换人 / 抽牌 / 进入选色时（{@code stateKey} 变化 → 计时清零）数字自然跟着变；</li>
     *   <li>颜色分段：&gt;15 秒绿、6~15 秒黄、≤5 秒红色加粗 —— 最后 5 秒一眼能看出紧张。</li>
     * </ul>
     */
    private void tickCountdown(int actor) {
        if (autoPlayed(actor)) {
            setCountdownText(null);
            return;
        }
        int remain = Math.max(0,
                (actionLimit - actionTicks + TICKS_PER_SECOND - 1) / TICKS_PER_SECOND);
        String color = remain <= 5 ? "§c§l" : (remain <= 15 ? "§e" : "§a");
        String who = seatName(actor);
        if (who.length() > 12) {
            who = who.substring(0, 12);
        }
        setCountdownText("§e轮到 " + who + "\n§7剩余 " + color + remain + "§7 秒");
    }

    /**
     * 更新牌桌上方的悬浮倒计时牌子；内容没变就什么都不做（不重复发包）。
     *
     * @param text 两行文字（支持 {@code §} 颜色码与 {@code \n}）；{@code null} = 摘掉牌子
     */
    private void setCountdownText(String text) {
        String next = (text == null || text.isEmpty()) ? null : text;
        if (next == null ? countdownText == null : next.equals(countdownText)) {
            return;
        }
        countdownText = next;
        if (countdown != null && !countdown.isClosed()) {
            countdown.setFloatingText(next);
        }
    }

    /** 人类超时：摸一张后直接过（避免离席卡死整桌）。 */
    private void timeoutAction(int seat) {
        if (!forceSafeAction(seat)) {
            return;
        }
        Player p = online[seat];
        if (p != null) {
            p.sendTip("§e思考超时，已自动代打。");
        }
        broadcast("§7" + seatName(seat) + " §7思考超时，系统自动代打。");
        afterAction();
    }

    /**
     * 一定能让回合有进展的安全动作：先手选色 → 红；已摸牌 → 过；否则摸一张再考虑过。
     *
     * @return true = 确实执行了动作（调用方负责 {@link #afterAction()}）
     */
    private boolean forceSafeAction(int seat) {
        int g = gameOfSeat[seat];
        if (game == null || g < 0) {
            return false;
        }
        if (game.isStartColorPending()) {
            return game.chooseStartColor(g, UnoDeck.COLOR_RED) == null;
        }
        if (game.hasDrawn()) {
            return game.pass(g) == null;
        }
        if (game.draw(g) != null) {
            return false;
        }
        if (game.phase() == UnoGame.PHASE_PLAYING && game.hasDrawn()) {
            game.pass(g);
        }
        return true;
    }

    /** 机器人 / 托管行动。 */
    private void autoAction(int seat, int level) {
        int g = gameOfSeat[seat];
        UnoAi ai = new UnoAi(level, random);
        if (game.isStartColorPending()) {
            if (game.chooseStartColor(g, ai.chooseColor(game.hand(g))) == null) {
                afterAction();
            }
            return;
        }
        if (game.hasDrawn()) {
            int drawn = game.drawnCard();
            boolean legal = game.playableCards(g).contains(drawn);
            if (ai.shouldPlayDrawn(drawn, game.hand(g), legal)) {
                applyPlay(seat, drawn, UnoDeck.isWild(drawn) ? ai.chooseColor(game.hand(g)) : -1, true);
            } else if (game.pass(g) == null) {
                broadcast("§7" + seatName(seat) + " §7摸牌后不出。");
                afterAction();
            }
            return;
        }
        int nextGame = Math.floorMod(game.currentSeat() + game.direction(), gamePlayers);
        int nextSeat = seatOfGame[nextGame];
        int nextHand = game.handSize(gameOfSeat[nextSeat]);
        UnoAi.Decision d = ai.decide(game.hand(g), game.playableCards(g),
                game.activeColor(), nextHand);
        if (d.draw()) {
            if (game.draw(g) == null && game.phase() == UnoGame.PHASE_PLAYING) {
                broadcast("§7" + seatName(seat) + " §7摸了一张牌。");
            }
            afterAction();
        } else {
            applyPlay(seat, d.cardId(), d.chosenColor(), true);
        }
    }

    /**
     * 出牌统一入口（人类 / 机器人共用）。
     *
     * @param silent 机器人 / 托管时为 true，播报措辞与失败兜底不同
     */
    private void applyPlay(int seat, int cardId, int chosenColor, boolean silent) {
        int g = gameOfSeat[seat];
        String err = game.play(g, cardId, chosenColor);
        if (err != null) {
            if (!silent) {
                Player p = online[seat];
                // 被拒时一定要解开「野牌待选色」：选色态的按钮组只有四个颜色，
                // 没有取消 / 抽牌 / 跳过，留着它就等于把玩家锁死在选色界面里。
                if (pendingWild[seat] >= 0) {
                    pendingWild[seat] = -1;
                    flush();
                }
                if (p != null) {
                    p.sendTip("§c" + err);
                }
                return;
            }
            // 机器人给不出合法牌（例如规则边界）：降级为「摸一张 / 过」，绝不递归重试
            pluginLog("机器人出牌被拒（seat=" + seat + " card=" + cardId + "）：" + err);
            if (game.hasDrawn()) {
                game.pass(g);
            } else {
                String derr = game.draw(g);
                if (derr == null && game.phase() == UnoGame.PHASE_PLAYING && game.hasDrawn()) {
                    game.pass(g);
                }
            }
            afterAction();
            return;
        }
        selected[seat] = -1;
        pendingWild[seat] = -1;
        broadcast("§f" + seatName(seat) + " §7出 §e" + UnoDeck.name(cardId)
                + (UnoDeck.isWild(cardId) ? " §7（定色：§f" + UnoDeck.colorName(chosenColor) + "§7）" : ""));
        // 这张牌从出牌者的手牌中心飞到他的出牌区（与 zone 变更同一批同步发出去）
        triggerFlight(false);
        // 只剩 1 张 → 自动喊 UNO
        if (game.handSize(g) == 1) {
            playSound(SND_UNO_CALL);
            broadcast("§c§l" + seatName(seat) + " 喊了 UNO！只剩最后一张！");
        }
        afterAction();
    }

    /** 机器人异常只在控制台留痕，不刷屏玩家聊天。 */
    private void pluginLog(String message) {
        Server.getInstance().getLogger().warning("[UNO] " + message);
    }

    /** 任意成功动作后的统一收尾：结算检测 + 计时重置 + 同步。 */
    private void afterAction() {
        if (game.phase() == UnoGame.PHASE_FINISHED) {
            doFinish();
            return;
        }
        pendingWild[0] = pendingWild[1] = pendingWild[2] = pendingWild[3] = -1;
        // 换人即解锁：摸牌锁定只在「仍是当前行动方」时有意义。
        // 摸牌本身不推进回合（actorSeat() 仍是本人）→ 锁定保留；出牌/跳过/超时代打都会
        // 推进回合 → 本人已不是行动方 → 锁定自动解除，不会把下一轮的选牌也一起锁掉。
        int act = actorSeat();
        for (int s = 0; s < 4; s++) {
            if (s != act) {
                selectLocked[s] = false;
            }
        }
        lastKey = stateKey();
        actionTicks = 0;
        actionLimit = computeActionLimit();
        dirty = true;
    }

    /** 结算：播报战报 → 经济结算 → 私聊明细 → 进入 SETTLED。 */
    private void doFinish() {
        if (settledFlag) {
            return;
        }
        settledFlag = true;
        broadcast("§6§l本局结束！");
        broadcast(game.summary());
        settleEconomy();
        showSettleBoard();
        phase = TablePhase.SETTLED;
        settleTicks = 0;
        selected[0] = selected[1] = selected[2] = selected[3] = -1;
        dirty = true;
        refreshViewers();
        // 结算界面：把在座玩家的表单换成「下一局 / 退出」
        manager.refreshSeatMenus(this);
    }

    /**
     * 经济结算。
     * <p>
     * 规则：
     * <ol>
     *     <li>每个输家应扣「剩余手牌分 × k」；</li>
     *     <li><b>扣到零为止</b>：应扣额大于余额时只扣余额（{@code 实扣 = min(应扣, 余额)}），余额不会变负；</li>
     *     <li>把各家<b>实扣额</b>累加成奖池；</li>
     *     <li>对奖池<b>整体</b>抽水（{@code gambling.cut %}）；</li>
     *     <li>税后金额全部给赢家。</li>
     * </ol>
     * 只统计<b>人类</b>座位（机器人不参与资金往来）；赢家是机器人时不动账。
     * {@code k == 0} 是免费局（应扣恒为 0），直接跳过。
     */
    private void settleEconomy() {
        java.util.Arrays.fill(settlePaid, 0);
        settlePrize = 0;
        if (coefficient <= 0) {
            broadcast("§7本桌倍数为 0（免费局），本局不进行金钱结算。");
            return;
        }
        int winnerGame = game.winnerSeat();
        if (winnerGame < 0) {
            broadcast("§7牌堆耗尽，本局无人出完，不进行结算。");
            return;
        }
        int winnerSeat = seatOfGame[winnerGame];
        if (humans[winnerSeat] == null) {
            broadcast("§7赢家是机器人，本局不进行结算。");
            return;
        }
        double cut = manager.config().getGambling().normalizedCut();
        double pot = 0;
        for (int s = 0; s < 4; s++) {
            if (s == winnerSeat || humans[s] == null) {
                continue;
            }
            int g = gameOfSeat[s];
            if (g < 0) {
                continue;
            }
            double owed = game.handPoints(g) * coefficient;
            UUID id = humans[s];
            Player p = online[s];
            // 「扣到零为止」：应扣大于余额时只扣余额，绝不出现负数余额
            double paid = Math.min(owed, Math.max(0.0, EconomyHook.balance(id)));
            if (paid <= 0) {
                if (owed > 0 && p != null) {
                    p.sendMessage("§c[UNO] §7本局剩余 " + game.handSize(g) + " 张 / "
                            + game.handPoints(g) + " 分，应付 §e" + fmt(owed)
                            + "§7，但余额为 0，无款可扣。");
                }
                continue;
            }
            if (!EconomyHook.reduce(id, paid)) {
                if (p != null) {
                    p.sendMessage("§c[UNO] §7本局应付 §e" + fmt(owed)
                            + "§7，但扣款失败，未计入奖池。");
                }
                continue;
            }
            settlePaid[s] = paid;
            pot += paid;
            if (p != null) {
                p.sendMessage("§c[UNO] §7本局剩余 " + game.handSize(g) + " 张 / "
                        + game.handPoints(g) + " 分，实扣 §e" + fmt(paid)
                        + "§7（倍数 " + fmt(coefficient) + "）"
                        + (paid < owed ? "§7，余额已扣到 0。" : "§7。"));
            }
        }
        if (pot <= 0) {
            broadcast("§7本局无人有款可扣，奖池为空，赢家未获得奖金。");
            return;
        }
        double commission = Math.round(pot * cut / 100.0 * 100.0) / 100.0;
        double prize = Math.round((pot - commission) * 100.0) / 100.0;
        settlePrize = prize;
        EconomyHook.add(humans[winnerSeat], prize);
        broadcast("§6经济结算：各家实扣合计 §e" + fmt(pot) + "§6，官方抽水 §e"
                + fmt(commission) + "§6（" + fmt(cut) + "%），" + seatName(winnerSeat)
                + "§6 实得 §e" + fmt(prize) + "§6。");
    }

    // ==================================================================
    // 结算 / 重开
    // ==================================================================

    /**
     * 结算展示板（对齐斗地主样式）：桌心一块「§l§e第N局 · X获胜」标题 +
     * 各座位出牌区上方一块「P1 · 名字 · 剩X张 / ±分 → ¥」明细，全部是隐形实体的
     * name tag（始终面向玩家的悬浮字），贴着桌面上方摆、直到离开结算阶段才收。
     */
    private void showSettleBoard() {
        int wg = game != null ? game.winnerSeat() : -1;
        int winnerSeat = wg >= 0 ? seatOfGame[wg] : -1;
        // 赢家总得分 = Σ其余各家剩余手牌分（官方记分）
        int winnerPts = 0;
        for (int s = 0; s < 4; s++) {
            if (s != winnerSeat && gameOfSeat[s] >= 0) {
                winnerPts += game.handPoints(gameOfSeat[s]);
            }
        }
        String title = winnerSeat >= 0
                ? "§l§e第" + roundNumber + "局 · " + seatOccupantLabel(winnerSeat) + "获胜"
                : "§l§e第" + roundNumber + "局 · 无人出完";
        putSettleText(0, origin.x, origin.y + COUNTDOWN_LIFT, origin.z, title);
        for (int s = 0; s < 4; s++) {
            int g = gameOfSeat[s];
            String text = null;
            if (g >= 0) {
                int pts = game.handPoints(g);
                String line1;
                String line2;
                if (s == winnerSeat) {
                    line1 = "§a§lP" + (s + 1) + " · " + seatOccupantLabel(s) + " 获胜";
                    line2 = coefficient > 0
                            ? "§e+" + winnerPts + "分 → ¥" + fmt(settlePrize)
                            : "§e+" + winnerPts + "分";
                } else {
                    line1 = "§fP" + (s + 1) + " · " + seatOccupantLabel(s)
                            + " §7剩" + game.handSize(g) + "张";
                    line2 = coefficient > 0
                            ? "§c-" + pts + "分 → ¥" + fmt(settlePaid[s])
                            : "§c-" + pts + "分";
                }
                text = line1 + "\n" + line2;
            }
            // 出牌区正上方（客户端布局 = OUT*13.5 模型单位，16 单位 = 1 格）
            double x = center.x + UnoTableRay.OUT_X[s] * (13.5 / 16.0);
            double z = center.z + UnoTableRay.OUT_Z[s] * (13.5 / 16.0);
            putSettleText(s + 1, x, origin.y + 0.3, z, text);
        }
    }

    /** 生成（或复用）第 i 块结算文字实体；text 为 null 表示隐藏该块。 */
    private void putSettleText(int i, double x, double y, double z, String text) {
        UnoClickBoxEntity b = settleBoard[i];
        if (text == null) {
            if (b != null && !b.isClosed()) {
                b.close();
            }
            settleBoard[i] = null;
            settleText[i] = null;
            return;
        }
        if (b == null || b.isClosed()) {
            Entity e = Entity.createEntity(UnoClickBoxEntity.IDENTIFIER,
                    Position.fromObject(new Vector3(x, y, z), level));
            if (!(e instanceof UnoClickBoxEntity box)) {
                return;
            }
            b = box;
            settleBoard[i] = b;
            settleText[i] = null;
            b.spawnToAll();
        }
        if (!text.equals(settleText[i])) {
            settleText[i] = text;
            b.setFloatingText(text);
        }
    }

    /** 收起结算展示板（下一局 / 退回等待 / 拆桌时）。 */
    private void closeSettleBoard() {
        for (int i = 0; i < settleBoard.length; i++) {
            if (settleBoard[i] != null && !settleBoard[i].isClosed()) {
                settleBoard[i].close();
            }
            settleBoard[i] = null;
            settleText[i] = null;
        }
    }

    private void tickSettled() {
        if (++settleTicks < SETTLE_INTERVAL) {
            return;
        }
        // 无人点「下一局」：退回等待，保留座位与机器人
        resetToWaiting();
    }

    private void resetToWaiting() {
        phase = TablePhase.WAITING;
        closeSettleBoard();
        game = null;
        gamePlayers = 0;
        java.util.Arrays.fill(gameOfSeat, -1);
        selected[0] = selected[1] = selected[2] = selected[3] = -1;
        pendingWild[0] = pendingWild[1] = pendingWild[2] = pendingWild[3] = -1;
        clearHover();
        lastKey = -1;
        settledFlag = false;
        broadcast("§7本局已收档，等待任意在座玩家点「开始游戏」开下一局。");
        refreshViewers();
        dirty = true;
        manager.markDirty();
        manager.refreshSeatMenus(this);
    }

    /** 清空全部座位的准星高亮。 */
    private void clearHover() {
        hover[0] = hover[1] = hover[2] = hover[3] = UnoTableEntity.HOVER_NONE;
    }

    /**
     * 开一局（含自动定庄）。
     *
     * @return null 表示已开始，否则为拒绝原因
     */
    public String startRound() {
        if (phase == TablePhase.DEALER_DRAW || phase == TablePhase.PLAYING) {
            return "本局正在进行中。";
        }
        if (occupiedSeats() < 2) {
            return "至少需要 2 个座位（玩家或人机）才能开局。";
        }
        String stake = checkStakeBalance();
        if (stake != null) {
            return stake;
        }
        buildMapping();
        closeSettleBoard();
        game = new UnoGame(gamePlayers, random);
        roundNumber++;
        phase = TablePhase.DEALER_DRAW;
        dealerIdx = 0;
        dealerStep = 0;
        dealerShowTicks = 0;
        dealerTie = 0;
        settledFlag = false;
        selected[0] = selected[1] = selected[2] = selected[3] = -1;
        pendingWild[0] = pendingWild[1] = pendingWild[2] = pendingWild[3] = -1;
        lastKey = -1;
        broadcast("§e第 " + roundNumber + " 局开始定庄：四家同时各抽一张牌比大小，展示 2 秒。");
        // 开局发放「定位器」（背包里没有才发）：手持它右键时客户端一定会把"使用物品"
        // 事务发到服务端，悬空的手牌/桌面按钮也就一定能被点中（见 LocatorItem 的说明）。
        for (int s = 0; s < 4; s++) {
            Player p = online[s];
            if (p != null && p.isOnline()) {
                manager.ensureLocator(p);
            }
        }
        manager.closeSeatMenus(this);
        dirty = true;
        return null;
    }

    /**
     * 开局前的经济门槛。
     * <p>
     * 本桌按「剩余手牌分 × k」结算，所以只要 <b>k &gt; 0</b>，每个<b>真人</b>座位的余额
     * 都必须<b>大于等于</b>配置门槛（{@code gambling.minStartBalance}，默认 10000），
     * 否则拒绝开局并把「无法开局」的原因回给调用方。
     * <p>
     * {@code k == 0} 是免费局（不扣钱、不抽水），此时不做余额校验；
     * 机器人不参与金钱往来，同样不校验。
     *
     * @return null 表示通过，否则为拒绝原因
     */
    private String checkStakeBalance() {
        if (coefficient <= 0) {
            return null;
        }
        double need = manager.config().getGambling().normalizedMinStartBalance();
        for (int s = 0; s < 4; s++) {
            UUID id = humans[s];
            if (id == null) {
                continue;
            }
            double bal = Math.max(0.0, EconomyHook.balance(id));
            if (bal < need) {
                return "无法开局：" + seatName(s) + " 余额不足，"
                        + "倍数 " + fmt(coefficient) + " 时要求余额大于等于 " + fmt(need)
                        + "（当前 " + fmt(bal) + "）。";
            }
        }
        return null;
    }

    /** 按座位升序建立「局内编号 ↔ 牌桌座位」映射（升序即顺时针序）。 */
    private void buildMapping() {
        java.util.Arrays.fill(gameOfSeat, -1);
        gamePlayers = 0;
        for (int s = 0; s < 4; s++) {
            if (isOccupied(s)) {
                gameOfSeat[s] = gamePlayers;
                seatOfGame[gamePlayers] = s;
                gamePlayers++;
            }
        }
    }

    // ==================================================================
    // 属性同步
    // ==================================================================

    /** 全量属性同步（批量一次发包）。 */
    private void sync() {
        if (visual == null || visual.isClosed()) {
            return;
        }
        visual.beginBatch();

        int[] zones = new int[UnoTableEntity.CARD_SLOTS];
        if (game != null) {
            for (int s = 0; s < 4; s++) {
                int g = gameOfSeat[s];
                if (g < 0) {
                    continue;
                }
                for (int id : game.hand(g)) {
                    zones[id] = UnoTableEntity.ZONE_HAND_BASE + s;
                }
            }
            // 定庄展示：四张比大小的牌**各挂在对应座位的手牌区**（区值 1..4）+
            // table 的展示位 = 1；客户端在展示态把它们平铺到「该座位自己的出牌区」
            // （谁抽到的牌就摆在哪一侧，见 build_table 的 card_N 与 UnoTableEntity.SHOW_SHIFT）。
            // 展示只用 2 秒，随后 deal() 会把 dealerDraw 清掉，这几张牌再也不会显示
            // （它们可能被洗回牌堆发到玩家手上）。
            if (dealerShowing()) {
                for (int g = 0; g < gamePlayers; g++) {
                    int card = game.dealerDraw(g);
                    int seat = seatOfGame[g];
                    if (card >= 0 && seat >= 0) {
                        zones[card] = UnoTableEntity.ZONE_HAND_BASE + seat;
                    }
                }
            }
            // 台面上**永远保留上一张真正打出的牌**：弃牌堆顶 = 当前有效牌，从翻起始牌到本局结束
            // 一直存在（跳过 / 摸牌不出都不换牌，只有真的出牌才被下一张顶掉）。
            int top = game.topCard();
            if (top >= 0) {
                zones[top] = UnoTableEntity.ZONE_DISCARD;
            }
        }
        visual.setCardZones(zones);

        for (int s = 0; s < 4; s++) {
            if (selected[s] >= 0 && !ownsCard(s, selected[s])) {
                selected[s] = -1;
            }
            visual.setSelected(s, selected[s]);
            visual.setHover(s, hover[s]);
        }
        visual.setTableState(tableState());
        visual.setControls(UnoTableEntity.packControls(globalButtons()));
        visual.setPile(pileCount());
        visual.setDeal(dealShown);
        visual.setSeats(seatsState());
        visual.setFly(flyValue);
        visual.endBatch();
    }

    /**
     * 打包 {@code uno_seats}：每座位 2 位，0 = 正常 / 1 = 托管 / 2 = 离线托管。
     * <p>
     * 客户端据此决定要不要画那个站在手牌旁边的小机器人（几何体的 {@code bot_N} 骨骼）。
     * 机器人本身由玩家占位，所以这里只反映「谁来代打」，不表示座位被机器人占用；
     * 断线（{@code online == null}）同样由系统代打，所以也画机器人。
     */
    private int seatsState() {
        int value = 0;
        for (int s = 0; s < 4; s++) {
            int code = 0;
            if (humans[s] != null) {
                // 离线一律算「离线托管」（与 autoPlayed 的判定一致），在座才看托管开关
                code = online[s] == null ? 2 : (trusted[s] ? 1 : 0);
            }
            value |= (code & 3) << (UnoTableEntity.SEAT_BITS * s);
        }
        return value;
    }

    private boolean ownsCard(int seat, int cardId) {
        int g = gameOfSeat[seat];
        return g >= 0 && game != null && game.hand(g).contains(cardId);
    }

    private int pileCount() {
        if (game == null) {
            return 0;
        }
        // 需求：中间牌堆永远只堆 5 张「?」，不暴露真实张数
        return game.drawPileSize() > 0 ? 5 : 0;
    }

    /** 当前全局按钮组（同一时刻只有行动方看得到）。 */
    private int[] globalButtons() {
        if (phase == TablePhase.SETTLED) {
            return UnoTableEntity.BTN_SETTLE;
        }
        int actor = actorSeat();
        if (actor < 0 || phase != TablePhase.PLAYING || dealing()) {
            return UnoTableEntity.BTN_NONE;
        }
        return buttonsFor(actor);
    }

    /** 指定座位的按钮组。 */
    private int[] buttonsFor(int seat) {
        if (phase == TablePhase.SETTLED) {
            return UnoTableEntity.BTN_SETTLE;
        }
        if (phase != TablePhase.PLAYING || game == null || dealing()) {
            return UnoTableEntity.BTN_NONE;
        }
        if (game.isStartColorPending() || pendingWild[seat] >= 0) {
            return UnoTableEntity.BTN_COLOR;
        }
        return game.hasDrawn() ? UnoTableEntity.BTN_DRAWN : UnoTableEntity.BTN_PLAY;
    }

    private int tableState() {
        int dealer = 0;
        int actor = 0;
        int acolor = 0;
        int dir = 0;
        // 中央那张牌是谁打出的 —— 客户端据此把它摆到那个座位自己的出牌区
        // （自己出的牌在自己这一侧、对手的牌贴对面那侧），见 build_model.PLAY_R。
        int dseat = 0;
        if (game != null) {
            if (game.dealerSeat() >= 0) {
                dealer = seatOfGame[game.dealerSeat()] + 1;
            }
            int a = actorSeat();
            if (a >= 0) {
                actor = a + 1;
            }
            acolor = Math.max(0, game.activeColor());
            dir = game.direction() > 0 ? 0 : 1;
            int lp = game.lastPlaySeat();
            if (lp >= 0 && lp < gamePlayers) {
                dseat = seatOfGame[lp] + 1;
            } else if (game.dealerSeat() >= 0) {
                // 还没人出牌 → 台面上那张是**起始牌**（发完 7 张后从牌堆翻开的那张），
                // 需求：它摆在**庄家面前**。之后第一次出牌就会把它顶掉。
                dseat = seatOfGame[game.dealerSeat()] + 1;
            }
        }
        int owner = phase == TablePhase.SETTLED
                ? UnoTableEntity.BTN_ALL
                : actor;
        return UnoTableEntity.tableState(dealer, actor, owner, acolor, dir, dseat,
                dealerShowing() ? 1 : 0);
    }

    // ==================================================================
    // 射线 hover
    // ==================================================================

    /**
     * 以本桌基准做一次射线拾取：能行动的座位给「自己的手牌 + 当前按钮组」，
     * 否则退化为「当前行动方的牌面（不可点）+ 空按钮组」。
     *
     * @return 命中（含 hover 槽位 / 命中点牌面局部坐标 (u, v) / 手牌区内展示序号）
     */
    private UnoTableRay.Hit raycast(Player p, int seat) {
        boolean act = canAct(seat);
        int[] hand = ownHandArray(seat);
        int[] buttons = act ? globalButtons() : EMPTY_BUTTONS;
        int actor = act ? seat : actorSeat();
        return UnoTableRay.raycast(p, origin.x, origin.y, origin.z,
                seat, actor, hand, buttons, selected[seat]);
    }

    /** 每 2 表 tick 重算各座位准星值。 */
    private void updateHover() {
        for (int s = 0; s < 4; s++) {
            Player p = online[s];
            if (p == null || !p.isOnline()) {
                if (hover[s] != UnoTableEntity.HOVER_NONE) {
                    hover[s] = UnoTableEntity.HOVER_NONE;
                    dirty = true;
                }
                continue;
            }
            UnoTableRay.Hit hit = raycast(p, s);
            if (hit.hover() != hover[s]) {
                hover[s] = hit.hover();
                dirty = true;
            }
        }
    }

    /**
     * 「定位器」激光点的常驻刷新（由 {@link UnoManager#tickLocatorDots()} 每 tick 调用）。
     * <p>
     * 需求（2026-10-15）：先要「常驻显示不闪」，后又要「做成像黑色框那样的，是在平面上的」
     * —— 粒子方案（朝向镜头的小方片）贴在 65° 斜面上永远有悬浮/穿模感，就此退役；
     * 激光点现在是模型里的薄片骨骼 {@code laser_dot}，与手牌/按钮用同一套布局表达式定位。
     * <p>
     * 这里每 tick 做的事：对每个「手持定位器 + 激光开」的座位做一次射线拾取，把命中点的
     * <b>牌面局部坐标 (u, v)</b>（见 {@link UnoTableRay#rectHit}）量化后写进
     * {@link UnoTableEntity#P_LASER_U} / {@code P_LASER_V}；未命中 / 没拿定位器 / 激光关
     * 则写保留值 127（该座位隐藏）。客户端用自己座位那份坐标，把自己视角里对应的牌面
     * 位置算出来叠上去 —— 与牌面完全共面，四人同时持定位器互不干扰。
     * <p>
     * 命中时顺带把 {@code hover} 一并刷新（平时 hover 每 2 tick 才更新一次），
     * 保证「激光指向哪张牌」与「哪张牌高亮」永远同步。
     */
    void tickLocatorDots() {
        if (visual == null || visual.isClosed()) {
            return;
        }
        // 空桌：无人入座必然无人持定位器，跳过每 tick 的 4 次手持判断 + 12 次属性写（缓存 no-op）
        if (occupiedSeats() == 0) {
            return;
        }
        for (int s = 0; s < 4; s++) {
            int uq = UnoTableEntity.LASER_NONE;
            int vq = UnoTableEntity.LASER_NONE;
            int sq = UnoTableEntity.LASER_NONE;
            Player p = online[s];
            if (p != null && p.isOnline()
                    && p.getInventory().getItemInHand() instanceof LocatorItem
                    && manager.isLaserOn(p)) {
                UnoTableRay.Hit hit = raycast(p, s);
                if (hit.hover() != UnoTableEntity.HOVER_NONE) {
                    uq = quantizeLaser(hit.u(), UnoTableEntity.LASER_U_OFFSET);
                    // 命中平面贴着「选中抬起后」的牌面，而客户端激光表达式没有选中抬升项
                    // （sv 是绝对槽号，客户端换算不出区内序号）—— 抬升 = RAISE 沿 V 轴，
                    // 这里直接折进 v，让坐标回到「未抬起」基准（与动画中心同一把尺）。
                    double v = hit.v();
                    if (hit.index() >= 0 && hit.hover() == UnoTableEntity.hoverCard(selected[s])) {
                        v += UnoTableRay.RAISE;
                    }
                    vq = quantizeLaser(v, UnoTableEntity.LASER_V_OFFSET);
                    if (hit.index() >= 0) {
                        sq = hit.index();
                    }
                    if (hit.hover() != hover[s]) {
                        hover[s] = hit.hover();
                        dirty = true;
                    }
                }
            }
            visual.setLaserU(s, uq);
            visual.setLaserV(s, vq);
            visual.setLaserS(s, sq);
        }
    }

    /** 牌面局部坐标 → 7 位打包值（0.125 单位精度）；越界钳到有效区间，不碰保留值 127。 */
    private static int quantizeLaser(double value, double offset) {
        int q = (int) Math.round((value + offset) * 8.0);
        return Math.max(0, Math.min(100, q));
    }

    /** 某座位手牌的卡槽数组（升序 = 展示顺序）。 */
    private int[] ownHandArray(int seat) {
        int g = gameOfSeat[seat];
        if (game == null || g < 0) {
            return EMPTY_HAND;
        }
        List<Integer> hand = game.hand(g);
        int[] out = new int[hand.size()];
        for (int i = 0; i < out.length; i++) {
            out[i] = hand.get(i);
        }
        return out;
    }

    // ==================================================================
    // 动画 / 声音 / 消息
    // ==================================================================

    private Collection<Player> viewers() {
        List<Player> out = new ArrayList<>(4);
        for (int s = 0; s < 4; s++) {
            if (online[s] != null && online[s].isOnline()) {
                out.add(online[s]);
            }
        }
        return out;
    }

    private void sendAnim(String animation, Collection<Player> players) {
        if (visual == null || visual.isClosed() || players.isEmpty()) {
            return;
        }
        // controller 只是一个「同类动画互相顶替」的分组标签（Bedrock 默认值 __runtime_controller）：
        // viewer_p0..p3 与 hidden 共用同一标签，才能保证切换视角时旧的被新的一把顶掉。
        AnimateEntityPacket.Animation anim = AnimateEntityPacket.Animation.builder()
                .animation(animation)
                .controller("tabletopgame:uno_viewer")
                .stopExpression("0")
                .blendOutTime(0f)
                .build();
        Entity.playAnimationOnEntities(anim, List.<Entity>of(visual), players);
    }

    /** 入座者看自家视角（viewer_pN），附近非入座者隐藏牌面（hidden）。 */
    private void refreshViewers() {
        if (visual == null || visual.isClosed()) {
            return;
        }
        // 空桌（无人在座）没有牌面需要隐藏、也没有观战者需要同步，
        // 直接跳过 —— 避免每 1 秒遍历整关卡玩家表 + 空发动画包
        if (occupiedSeats() == 0) {
            return;
        }
        for (int s = 0; s < 4; s++) {
            Player p = online[s];
            if (p != null && p.isOnline()) {
                sendAnim("animation.tabletopgame.uno.viewer_p" + s, List.of(p));
            }
        }
        List<Player> spectators = new ArrayList<>();
        for (Player p : level.getPlayers().values()) {
            if (p.distanceSquared(center) > SPECTATOR_RANGE * SPECTATOR_RANGE) {
                continue;
            }
            if (isSeated(p.getUniqueId())) {
                continue;
            }
            spectators.add(p);
        }
        if (!spectators.isEmpty()) {
            sendAnim("animation.tabletopgame.uno.hidden", spectators);
        }
    }

    /** 自定义音效：只放给在座在线玩家。 */
    private void playSound(String sound) {
        Collection<Player> listeners = viewers();
        if (!listeners.isEmpty()) {
            level.addSound(center, sound, listeners.toArray(new Player[0]));
        }
    }

    private void broadcast(String message) {
        for (Player p : viewers()) {
            p.sendMessage("§b[UNO] " + message);
        }
    }

    // ==================================================================
    // 玩家交互
    // ==================================================================

    /**
     * 入座归位：把玩家摆到该座位的站位点，并转过身来面向棋心。
     * <p>
     * 复刻行为包 {@code D:\CodeProject\Gobang\斗地主\bp} 的做法（脚本里的 {@code Hg()}：
     * {@code player.teleport(棋心 + outward × 距离, {facingLocation: 棋心})}）。
     * 差别只有两点：距离换成 {@link #SEAT_STAND_RADIUS}（棋盘外隔 1 格），
     * 朝向因为没有 {@code facingLocation} 参数，就直接算成 yaw / pitch。
     *
     * @return null 表示已归位，否则是没能归位的原因
     */
    public String standAtSeat(Player p, int seat) {
        if (p == null || seat < 0 || seat > 3) {
            return "座位不合法。";
        }
        double x = center.x + UnoTableRay.OUT_X[seat] * SEAT_STAND_RADIUS;
        double z = center.z + UnoTableRay.OUT_Z[seat] * SEAT_STAND_RADIUS;

        // 站位那一列可能是墙或别的方块：往上找第一处「脚 + 头都空」的高度，
        // 既不挖方块，也不把玩家塞进方块里。
        int standY = Integer.MIN_VALUE;
        for (int dy = 0; dy <= SEAT_SEEK_UP; dy++) {
            if (isStandable(x, baseY + dy, z)) {
                standY = baseY + dy;
                break;
            }
        }
        if (standY == Integer.MIN_VALUE) {
            return seatLabel(seat) + " 那边的站位被方块挡住了。";
        }

        // 朝向棋心：yaw 与行为包 dB() 同一个约定 atan2(-dx, dz)；
        // 把 yaw/pitch 塞进 Location 再 teleport，传送包就会带上朝向。
        double dx = center.x - x;
        double dz = center.z - z;
        float yaw = (float) Math.toDegrees(Math.atan2(-dx, dz));
        double horiz = Math.max(0.001, Math.sqrt(dx * dx + dz * dz));
        double eyeY = standY + p.getEyeHeight();
        float pitch = (float) Math.toDegrees(
                Math.atan2(baseY + SEAT_FACE_TARGET_Y - eyeY, horiz));

        p.teleport(new Location(x, standY, z, yaw, pitch, level),
                PlayerTeleportEvent.TeleportCause.PLUGIN);
        p.setRotation(yaw, pitch);
        return null;
    }

    /** 该处能否站人：脚（y）与头（y+1）两格都不是实心方块。 */
    private boolean isStandable(double x, int y, double z) {
        int fx = (int) Math.floor(x);
        int fz = (int) Math.floor(z);
        return !level.getBlock(fx, y, fz).isSolid()
                && !level.getBlock(fx, y + 1, fz).isSolid();
    }

    /**
     * 入座指定座位。
     *
     * @return null 表示成功，否则为拒绝原因
     */
    public String join(Player p, int seat) {
        if (seat < 0 || seat > 3) {
            return "座位不合法。";
        }
        UUID id = p.getUniqueId();
        int existing = seatOf(id);
        if (existing == seat) {
            reattach(p);
            return null;
        }
        if (existing >= 0) {
            return "你已经坐在" + seatLabel(existing) + "了，请先退出。";
        }
        if (manager.getTableOf(id) != null) {
            return "你已坐在其他牌桌上，请先退出那张牌桌。";
        }
        if (isOccupied(seat)) {
            return seatLabel(seat) + "已经有人了，请换一个座位。";
        }
        humans[seat] = id;
        online[seat] = p;
        bots[seat] = -1;
        names[seat] = p.getName();
        if (firstJoiner == null) {
            firstJoiner = id;
        }
        manager.seat(id, this);
        releaseMenu(id);
        // 入座即归位：传送到本座位的站位点（棋心朝外 3 格）并转向棋心。
        String standErr = standAtSeat(p, seat);
        if (standErr != null) {
            p.sendTip("§e已入座，但没能归位：" + standErr);
        }
        manager.markDirty();
        refreshViewers();
        dirty = true;
        // 中途入座（对局已经开始）也要立刻拿到定位器，否则这一局里他点不动牌
        if (phase == TablePhase.DEALER_DRAW || phase == TablePhase.PLAYING) {
            manager.ensureLocator(p);
        }
        manager.refreshSeatMenus(this);
        return null;
    }

    /**
     * 补充一个机器人到下一个空位。
     *
     * @return null 表示成功，否则为拒绝原因
     */
    public String addBot(int level) {
        if (level < UnoAi.LEVEL_EASY || level > UnoAi.LEVEL_MASTER) {
            return "机器人档位不合法。";
        }
        if (phase == TablePhase.DEALER_DRAW || phase == TablePhase.PLAYING) {
            return "对局进行中，无法补充人机。";
        }
        int empty = -1;
        for (int s = 0; s < 4; s++) {
            if (!isOccupied(s)) {
                empty = s;
                break;
            }
        }
        if (empty < 0) {
            return "座位已满（4 人），无法再补充人机。";
        }
        bots[empty] = level;
        names[empty] = "机器人·" + UnoAi.levelName(level);
        manager.markDirty();
        broadcast("§7" + seatLabel(empty) + " 补充了 " + names[empty] + "。");
        dirty = true;
        manager.refreshSeatMenus(this);
        return null;
    }

    /** 清除全部机器人（对局中不允许）。 */
    public String clearBots() {
        if (phase == TablePhase.DEALER_DRAW || phase == TablePhase.PLAYING) {
            return "对局进行中，无法清除人机。";
        }
        boolean any = false;
        for (int s = 0; s < 4; s++) {
            if (bots[s] >= 0) {
                bots[s] = -1;
                names[s] = null;
                any = true;
            }
        }
        if (!any) {
            return "当前没有机器人。";
        }
        manager.markDirty();
        broadcast("§7已清除全部人机。");
        dirty = true;
        manager.refreshSeatMenus(this);
        return null;
    }

    /** 设定每分倍数 k（仅第一入座者）。只接受 0~1000 的整数；0 表示免费局。 */
    public String setCoefficient(Player p, double k) {
        if (!isFirstJoiner(p.getUniqueId())) {
            return "只有第一个入座的玩家可以设定倍数。";
        }
        if (phase == TablePhase.DEALER_DRAW || phase == TablePhase.PLAYING) {
            return "对局进行中，无法修改倍数。";
        }
        if (k < 0 || k > MAX_COEFFICIENT) {
            return "倍数需在 0 与 " + (long) MAX_COEFFICIENT + " 之间。";
        }
        if (k != Math.floor(k)) {
            return "倍数只能是整数。";
        }
        coefficient = k;
        manager.markDirty();
        broadcast("§7本桌倍数已设为 §e" + fmt(coefficient) + "§7"
                + (coefficient <= 0 ? "（免费局：不扣钱、不抽水）。" : "（赢家按各家剩余手牌分收取）。"));
        // 倍数会显示在各家菜单正文里，改完立即刷新所有在座玩家的表单
        manager.refreshSeatMenus(this);
        return null;
    }

    /** 读档时恢复倍数 k（无权限校验，仅供管理器调用）。 */
    public void restoreCoefficient(double k) {
        if (k >= 0 && k <= MAX_COEFFICIENT) {
            coefficient = Math.floor(k);
        }
    }

    /** 关闭所有在座玩家的牌桌表单（开局 / 结算切换时用）。 */
    public void closeAllMenus() {
        manager.closeSeatMenus(this);
    }

    /** 延后一 tick 重新弹出本牌桌菜单（避免在表单回调里直接弹窗造成客户端窗口冲突）。 */
    public void laterOpen(Player player) {
        manager.reopenMenu(player, this);
    }

    /** 延后一 tick 执行一段动作。 */
    public void laterOpen(Runnable action) {
        manager.runLater(action);
    }

    /** 断线重连 / 托管中回归：恢复在线。 */
    public boolean reattach(Player p) {
        int s = seatOf(p.getUniqueId());
        if (s < 0 || online[s] != null) {
            return false;
        }
        online[s] = p;
        // 人回来了就自动取消托管：否则玩家会「明明在线却被系统代打」，与斗地主插件一致
        if (trusted[s]) {
            trusted[s] = false;
            p.sendMessage("§b[UNO] §7已自动取消托管。");
        }
        manager.seat(p.getUniqueId(), this);
        refreshViewers();
        dirty = true;
        return true;
    }

    /** 该座位是否开着托管（玩家在座，但出牌权交给系统）。 */
    public boolean isTrusted(int seat) {
        return seat >= 0 && seat < 4 && trusted[seat];
    }

    /**
     * 切换本座位的托管：开启后轮到本人时由系统按机器人逻辑自动出牌。
     * <p>
     * 需求原话：「增加机器人托管，也就是像斗地主插件一样点击棋桌，可以选择托管按钮」。
     * 托管期间玩家仍在座（不腾位、不断线也不丢座位），客户端会在他的手牌左边
     * 画出那个小机器人（{@code uno_seats} 属性）；
     * 随时再点一次「取消托管」即可自己接着打（断线重连也会自动取消）。
     *
     * @return null 表示成功，否则为拒绝原因
     */
    public String toggleTrust(Player p) {
        int seat = seatOf(p.getUniqueId());
        if (seat < 0) {
            return "你不在牌桌上。";
        }
        trusted[seat] = !trusted[seat];
        broadcast("§7" + seatName(seat)
                + (trusted[seat] ? " §7开启了托管，轮到本人时由系统代打。" : " §7取消了托管。"));
        // 托管切换会改变本回合的「思考节奏」（人类 45 秒超时 ↔ 机器人 0.5~1.5 秒），
        // 正在思考时立刻按新节奏重新计时，不然要等满旧的时限才会动。
        if (phase == TablePhase.PLAYING && seat == actorSeat()) {
            actionTicks = 0;
            actionLimit = computeActionLimit();
            lastKey = stateKey();
        }
        dirty = true;
        flush();
        manager.refreshSeatMenus(this);
        return null;
    }

    /** 主动退出牌桌：对局进行中把座位交给系统托管（转为同档机器人）以保住本局。 */
    public void leave(Player p) {
        int s = seatOf(p.getUniqueId());
        if (s < 0) {
            p.sendTip("§e你不在牌桌上。");
            return;
        }
        leaveSeat(s);
        // 离桌即回收（需求：「结束对局的话，自动回收」；只动定位器，不碰别的物品）
        manager.takeLocator(p);
        p.sendTip("§e已退出牌桌。");
    }

    /** 断线：等待中直接腾位，对局 / 结算中转托管（保留座位以便重连）。 */
    public void onDisconnect(Player p) {
        int s = seatOf(p.getUniqueId());
        if (s < 0) {
            return;
        }
        if (phase == TablePhase.WAITING) {
            leaveSeat(s);
        } else {
            online[s] = null;
            broadcast("§7" + seatName(s) + " 断线，进入托管。");
            dirty = true;
        }
    }

    /** 腾出座位：对局中把该座位转成同档机器人，其余情况彻底腾空。 */
    private void leaveSeat(int seat) {
        UUID id = humans[seat];
        if (id != null) {
            manager.unseat(id);
        }
        trusted[seat] = false;
        boolean midGame = phase == TablePhase.DEALER_DRAW || phase == TablePhase.PLAYING;
        if (midGame && gameOfSeat[seat] >= 0) {
            // 对局中离座：转为同档机器人继续（玩家可用「清除人机」收回该座位）
            humans[seat] = null;
            online[seat] = null;
            bots[seat] = UnoAi.LEVEL_NORMAL;
            names[seat] = "机器人·" + UnoAi.levelName(UnoAi.LEVEL_NORMAL);
            broadcast("§7" + SEAT_LABEL[seat] + " 的玩家退出，已交给系统托管代打。");
        } else {
            humans[seat] = null;
            online[seat] = null;
            bots[seat] = -1;
            names[seat] = null;
        }
        if (id != null && id.equals(firstJoiner)) {
            firstJoiner = null;
            for (int s = 0; s < 4; s++) {
                if (humans[s] != null) {
                    firstJoiner = humans[s];
                    break;
                }
            }
        }
        if (occupiedSeats() == 0) {
            hover[0] = hover[1] = hover[2] = hover[3] = UnoTableEntity.HOVER_NONE;
            menuHolder = null;
        }
        manager.markDirty();
        refreshViewers();
        dirty = true;
        manager.refreshSeatMenus(this);
    }

    /** 点击牌桌（未入座）打开菜单。 */
    public void openMenu(Player p) {
        manager.openMenu(p, this);
    }

    /**
     * 右键牌桌的交互分派：先按准星命中手牌 / 按钮，未命中则打开菜单。
     * <p>与斗地主一致，但<b>不需要手持激光笔</b>。
     */
    public void useBoard(Player p) {
        useBoard(p, true);
    }

    /** 右键「空中」（准星没打中方块）：只认手牌 / 按钮命中，未命中不弹菜单。 */
    public boolean useBoardAir(Player p) {
        return useBoard(p, false);
    }

    /**
     * 右键牌桌的交互分派。
     *
     * @param allowMenu 没命中手牌 / 按钮时是否打开菜单。
     *                  <p><b>为什么需要这个开关</b>：手牌是<b>悬空</b>在台面上方的（第一行底边
     *                  离台面 0.26 格，第二行起更高），而基岩客户端的准星只会去命中<b>方块</b>
     *                  —— 瞄第二行及以上的手牌时准星打不到牌桌方块，客户端就只发来
     *                  「右键空中」（{@code RIGHT_CLICK_AIR}）事件。这类事件必须接受
     *                  （否则第二行手牌点不动），但它的准星本来就落在牌桌附近，
     *                  未命中时再弹菜单会变成误触，所以空中路径传 {@code false}。
     * @return 是否吃掉了这次点击（命中了手牌或按钮）
     */
    public boolean useBoard(Player p, boolean allowMenu) {
        UUID id = p.getUniqueId();
        int s = seatOf(id);
        if (s < 0) {
            if (allowMenu) {
                openMenu(p);
            }
            return false;
        }
        if (online[s] == null) {
            reattach(p);
        }
        if (phase == TablePhase.WAITING || phase == TablePhase.DEALER_DRAW) {
            if (allowMenu) {
                openMenu(p);
            }
            return false;
        }
        if (phase == TablePhase.SETTLED) {
            // 结算阶段按钮不依赖准星：直接打开菜单更稳（客户端按钮只在桌面上，点击易漏）
            int[] group = UnoTableEntity.BTN_SETTLE;
            int[] hand = EMPTY_HAND;
            int actor = s;
            UnoTableRay.Hit hit = UnoTableRay.raycast(p, origin.x, origin.y, origin.z,
                    s, actor, hand, group, -1);
            int btn = UnoTableEntity.hoveredButtonSlot(hit.hover());
            if (btn >= 0) {
                pressButton(p, s, btn);
                return true;
            }
            if (allowMenu) {
                openMenu(p);
            }
            return false;
        }
        int[] hand = ownHandArray(s);
        boolean act = canAct(s);
        int[] buttons = act ? globalButtons() : EMPTY_BUTTONS;
        int actor = act ? s : actorSeat();
        UnoTableRay.Hit hit = UnoTableRay.raycast(p, origin.x, origin.y, origin.z,
                s, actor, hand, buttons, selected[s]);
        int hv = hit.hover();
        if (hv == UnoTableEntity.HOVER_NONE) {
            if (allowMenu) {
                openMenu(p);
            }
            return false;
        }
        int card = UnoTableEntity.hoveredCardSlot(hv);
        if (card >= 0) {
            selectCard(p, s, card);
            return true;
        }
        int btn = UnoTableEntity.hoveredButtonSlot(hv);
        if (btn >= 0) {
            pressButton(p, s, btn);
            return true;
        }
        return false;
    }

    /** 点击手牌：切换选中（同槽再点取消）。 */
    private void selectCard(Player p, int seat, int cardId) {
        if (phase != TablePhase.PLAYING) {
            return;
        }
        if (seat != actorSeat()) {
            p.sendTip("§e还没轮到你。");
            return;
        }
        if (pendingWild[seat] >= 0) {
            // 逃生口：选色态只有四个颜色按钮，点手牌视为「取消这次出牌」。
            // 没有这条，任何意外（例如校验漏网）都会让玩家锁死在选色界面。
            pendingWild[seat] = -1;
            p.sendTip("§7已取消选色，重新点「出牌」可以再选一次。");
            flush();
        }
        if (selectLocked[seat]) {
            // 摸牌后的那张牌是强制选中的：别人（和别的牌）都不能把它「顶掉」，
            // 只能走「出牌」或「跳过」两条路，避免从高亮消失推断出摸到了什么牌。
            p.sendTip("§e请先点「出牌」或「跳过」。");
            return;
        }
        if (game.isStartColorPending()) {
            p.sendTip("§e请先选一个颜色。");
            return;
        }
        selected[seat] = selected[seat] == cardId ? -1 : cardId;
        flush();
    }

    /** 立即发包：选牌 / 按钮这类交互反馈要跟手，不能等到 tick 末尾。 */
    private void flush() {
        dirty = false;
        sync();
    }

    /** 按钮点击（index = 槽位下标）。 */
    private void pressButton(Player p, int seat, int index) {
        int[] group = buttonsFor(seat);
        if (index < 0 || index >= group.length || group[index] == 0) {
            return;
        }
        int code = group[index];
        switch (code) {
            case Controls.PLAY -> doPlayButton(p, seat);
            case Controls.DRAW -> doDraw(p, seat);
            case Controls.SKIP -> doSkip(p, seat);
            case Controls.HINT -> doHint(p, seat);
            case Controls.CANCEL_SELECT -> {
                if (selectLocked[seat]) {
                    // 摸牌后的强制选中不可取消（只能出牌或跳过），否则「取消」就等于
                    // 向所有人暴露「摸到的这张不能出」。
                    p.sendTip("§e请先点「出牌」或「跳过」。");
                    return;
                }
                selected[seat] = -1;
                pendingWild[seat] = -1;
                flush();
            }
            case Controls.NEXT -> doNext(p);
            case Controls.EXIT -> leave(p);
            case Controls.C_RED, Controls.C_YELLOW, Controls.C_GREEN, Controls.C_BLUE ->
                    doChooseColor(p, seat, code - Controls.C_RED);
            default -> {
            }
        }
    }

    /** 「出牌」：野牌先切到选色按钮组。 */
    private void doPlayButton(Player p, int seat) {
        if (seat != actorSeat()) {
            p.sendTip("§e还没轮到你。");
            return;
        }
        int card = game.hasDrawn() ? game.drawnCard() : selected[seat];
        if (card < 0) {
            p.sendTip("§e请先点击手牌选择要出的牌。");
            return;
        }
        if (UnoDeck.isWild(card)) {
            // 必须在进入选色态**之前**判定这张牌到底能不能出：选色态的按钮组只有
            // 四个颜色，没有「取消 / 抽牌 / 跳过」，一旦进来又出不了（典型：
            // 手里还有当前颜色的牌却打「+4 王牌」），玩家就被锁死在这里，只能等超时代打。
            String why = game.checkPlay(gameOfSeat[seat], card);
            if (why != null) {
                p.sendTip("§c" + why);
                return;
            }
            pendingWild[seat] = card;
            selected[seat] = card;
            p.sendTip("§e野牌需要先选一个颜色。");
            flush();
            return;
        }
        applyPlay(seat, card, -1, false);
    }

    /** 「选色」。 */
    private void doChooseColor(Player p, int seat, int color) {
        if (color < 0 || color >= UnoDeck.COLOR_COUNT) {
            return;
        }
        int g = gameOfSeat[seat];
        if (game.isStartColorPending()) {
            String err = game.chooseStartColor(g, color);
            if (err != null) {
                p.sendTip("§c" + err);
                return;
            }
            broadcast("§f" + seatName(seat) + " §7把起始颜色定为 §e"
                    + UnoDeck.colorName(color));
            afterAction();
            return;
        }
        int card = pendingWild[seat];
        if (card < 0) {
            p.sendTip("§e选色已失效，请重新点「出牌」。");
            return;
        }
        // 两次点击之间局面可能变了（超时代打 / 回合被推进），再校验一次；
        // 不通过就**解除选色态**，绝不能把玩家留在只有颜色按钮的界面里。
        String why = game.checkPlay(g, card);
        if (why != null) {
            pendingWild[seat] = -1;
            p.sendTip("§c" + why + "（已取消出牌）");
            flush();
            return;
        }
        applyPlay(seat, card, color, false);
    }

    /** 「抽牌」。 */
    private void doDraw(Player p, int seat) {
        if (seat != actorSeat()) {
            p.sendTip("§e还没轮到你。");
            return;
        }
        if (game.hasDrawn()) {
            p.sendTip("§e这一回合已经摸过牌了。");
            return;
        }
        String err = game.draw(gameOfSeat[seat]);
        if (err != null) {
            p.sendTip("§c" + err);
            return;
        }
        int drawn = game.phase() == UnoGame.PHASE_PLAYING ? game.drawnCard() : -1;
        if (drawn >= 0) {
            // 需求：摸到的那张牌必须「突出」并且**锁住**——玩家一眼就知道摸到的是哪张，
            // 而且高亮不会被准星扫过别的牌带走；只有「出牌 / 跳过」才解除（见 selectLocked）。
            selected[seat] = drawn;
            selectLocked[seat] = true;
            p.sendTip("§7你摸到了 §e" + UnoDeck.name(drawn) + "§7：可以「出牌」或「跳过」。");
            broadcast("§7" + seatName(seat) + " §7摸了一张牌。");
        }
        afterAction();
    }

    /** 「跳过」：摸牌后不出。 */
    private void doSkip(Player p, int seat) {
        if (seat != actorSeat()) {
            p.sendTip("§e还没轮到你。");
            return;
        }
        String err = game.pass(gameOfSeat[seat]);
        if (err != null) {
            p.sendTip("§c" + err);
            return;
        }
        selectLocked[seat] = false;
        selected[seat] = -1;
        broadcast("§7" + seatName(seat) + " §7摸牌后不出。");
        afterAction();
    }

    /** 「提示」：自动选中一张可出的牌（多次点击循环）。 */
    private void doHint(Player p, int seat) {
        if (seat != actorSeat()) {
            p.sendTip("§e还没轮到你。");
            return;
        }
        int g = gameOfSeat[seat];
        List<Integer> playable = game.playableCards(g);
        if (playable.isEmpty()) {
            p.sendTip("§7没有能出的牌，请「抽牌」。");
            return;
        }
        int pick = playable.get(hintIndex[seat] % playable.size());
        hintIndex[seat]++;
        selected[seat] = pick;
        p.sendTip("§7已选中 §e" + UnoDeck.name(pick) + "§7，点「出牌」打出。");
        flush();
    }

    /** 「下一局」：原座位直接再开一局。 */
    private void doNext(Player p) {
        if (phase != TablePhase.SETTLED) {
            return;
        }
        String err = startRound();
        if (err != null) {
            p.sendTip("§c" + err);
            resetToWaiting();
        }
    }

    // ==================================================================
    // 菜单展示
    // ==================================================================

    /** 表单正文：座位、倍数、桌主。 */
    public String statusText(Player viewer) {
        StringBuilder sb = new StringBuilder();
        // 用户 2026-10-16 指定的精简格式：只保留座位状态 / 倍数 / 桌主，
        // 其余（免费局说明、设定者、余额、开局要求提示）一律去掉。
        sb.append("§l座位状态\n");
        String[] dir = {"东侧", "南侧", "西侧", "北侧"};
        for (int s = 0; s < 4; s++) {
            sb.append("§rP").append(s + 1).append(": ")
                    .append(seatOccupantLabel(s)).append(" - ").append(dir[s]).append('\n');
        }
        sb.append("§l 当前倍数：§r").append(fmt(coefficient)).append('\n');
        sb.append("§l 当前桌主：§r");
        if (firstJoiner != null) {
            sb.append(manager.nameOf(firstJoiner));
        } else {
            sb.append("无");
        }
        return sb.toString();
    }

    /** 某座位占用者名（供新表单「P1: 玩家名 - 东侧」）：空闲→「空闲」，否则 = 玩家名 / 机器人名。 */
    public String seatOccupantLabel(int seat) {
        if (humans[seat] == null && bots[seat] < 0) {
            return "空闲";
        }
        return names[seat] != null ? names[seat] : "机器人";
    }

    /** 某座位的展示标签（供菜单）。 */
    public String seatSlotLabel(int seat) {
        if (bots[seat] >= 0) {
            return "§e" + seatName(seat) + " §8(人机)";
        }
        if (humans[seat] == null) {
            return "§8空位";
        }
        if (online[seat] == null) {
            return "§f" + seatName(seat) + " §8(离线·托管)";
        }
        if (trusted[seat]) {
            return "§f" + seatName(seat) + " §8(托管)";
        }
        return "§f" + seatName(seat);
    }

    /** 阶段中文名。 */
    public String stageLabel() {
        return switch (phase) {
            case WAITING -> occupiedSeats() >= 2 ? "等待点开始" : "等待入座";
            case DEALER_DRAW -> "定庄中（四家同时抽牌比大小，展示 2 秒）";
            case PLAYING -> {
                int a = actorSeat();
                yield game != null && game.isStartColorPending()
                        ? "等待 " + seatName(a) + " 选起始颜色"
                        : "对局中，轮到 " + seatName(a)
                        + "（剩余牌堆 " + game.drawPileSize() + " 张）";
            }
            case SETTLED -> "本局结束，可点「下一局」或「退出」";
        };
    }
}
