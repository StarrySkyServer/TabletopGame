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
import cn.nukkit.event.player.PlayerMoveEvent;
import cn.nukkit.event.player.PlayerQuitEvent;
import cn.nukkit.item.Item;
import cn.nukkit.level.Level;
import cn.nukkit.level.Sound;
import cn.nukkit.math.BlockFace;
import cn.nukkit.math.Vector3;
import cn.nukkit.plugin.PluginBase;
import com.tabletopgame.ai.GoAi;
import com.tabletopgame.board.GoBoardBlock;
import com.tabletopgame.config.TabletopGameConfig;
import com.tabletopgame.entity.GoStoneEntity;
import com.tabletopgame.item.GoBoard13Item;
import com.tabletopgame.item.GoBoard19BigItem;
import com.tabletopgame.item.GoBoard19Item;
import com.tabletopgame.item.GoBoard9Item;
import com.tabletopgame.storage.BoardStorage;
import com.tabletopgame.ui.GoMenu;

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
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * 管理所有已放置的围棋棋盘：放置、破坏收回、菜单、落子交互、准星高亮与存档恢复。
 * <p>
 * 骨架对齐 {@link OthelloManager}，走独立存档文件 {@code go_boards.yml}。
 * 四种棋盘规格由物品决定：9 路 / 13 路用 2x2 方块，19 路用 3x3 或 4x4 方块。
 */
public class GoManager implements Listener {

    /** 放置棋盘的冷却时间（毫秒）：一次点击可能触发多个交互事件，需去重。 */
    private static final long PLACE_COOLDOWN_MS = 500L;

    /** 当前存档文件名（YAML）。 */
    private static final String STORAGE_FILE = "go_boards.yml";

    /** 旧版纯文本存档文件名，仅用于一次性迁移读取。 */
    private static final String LEGACY_STORAGE_FILE = "go_boards.txt";

    private final PluginBase plugin;
    private final TabletopGameManager gameManager;

    private final Map<String, GoBoard> boards = new HashMap<>();
    private final Map<UUID, Long> placeCooldown = new HashMap<>();
    private final Map<Level, List<GoBoard>> boardsByLevel = new HashMap<>();
    private final List<UUID> leftScratch = new ArrayList<>(4);
    private final Map<UUID, Integer> hoverTick = new HashMap<>();

    private boolean dirty;
    private boolean loadPending;
    private boolean restored;

    private final ExecutorService saveExecutor = Executors.newSingleThreadExecutor(task -> {
        Thread thread = new Thread(task, "Go-Save");
        thread.setDaemon(true);
        return thread;
    });

    public GoManager(PluginBase plugin, TabletopGameManager gameManager) {
        this.plugin = plugin;
        this.gameManager = gameManager;
    }

    public double playerRange() {
        return gameManager.playerRange();
    }

    public TabletopGameConfig config() {
        return gameManager.getConfig();
    }

    long menuLockMs() {
        return gameManager.getConfig().getMenuLockSeconds() * 1000L;
    }

    public void requestLoad() {
        this.loadPending = true;
    }

    void markDirty() {
        this.dirty = true;
    }

    private void indexBoard(GoBoard board) {
        boardsByLevel.computeIfAbsent(board.getLevel(), k -> new ArrayList<>(4)).add(board);
    }

    private void unindexBoard(GoBoard board) {
        List<GoBoard> list = boardsByLevel.get(board.getLevel());
        if (list != null) {
            list.remove(board);
            if (list.isEmpty()) {
                boardsByLevel.remove(board.getLevel());
            }
        }
    }

    private GoBoard findBoard(Level level, int x, int y, int z) {
        List<GoBoard> list = boardsByLevel.get(level);
        if (list == null) {
            return null;
        }
        for (int i = 0; i < list.size(); i++) {
            GoBoard board = list.get(i);
            if (board.contains(x, y, z)) {
                return board;
            }
        }
        return null;
    }

    /**
     * 注意：与五子棋一致，这里刻意不设置 {@code ignoreCancelled = true}。
     * <p>
     * 基岩触屏点击会走 {@code Level#useItemOn}，该路径可能在派发事件前因出生点保护
     * 对非 OP 玩家调用 {@code setCancelled(true)}；忽略已取消事件会导致出生点附近
     * 完全收不到回调。放置棋盘仍遵守取消逻辑（内部再判断）。
     */
    @EventHandler(priority = EventPriority.HIGH)
    public void onInteract(PlayerInteractEvent event) {
        if (event.getAction() != PlayerInteractEvent.Action.RIGHT_CLICK_BLOCK) {
            return;
        }
        Player player = event.getPlayer();
        int[] spec = specOf(event.getItem());
        if (spec != null) {
            if (event.isCancelled() || !canPlace(player)) {
                event.setCancelled(true);
                return;
            }
            tryPlace(player, event, spec[0], spec[1]);
            return;
        }
        Block clicked = event.getBlock();
        if (clicked instanceof GoBoardBlock) {
            event.setCancelled(true);
            GoBoard board = findBoard(player.getLevel(),
                    clicked.getFloorX(), clicked.getFloorY(), clicked.getFloorZ());
            if (board != null) {
                useBoard(player, board);
            }
        }
    }

    /** 棋盘物品 → {@code {路数, 方块边长}}；非围棋物品返回 null。 */
    private static int[] specOf(Item item) {
        if (item instanceof GoBoard9Item) {
            return new int[]{9, 2};
        }
        if (item instanceof GoBoard13Item) {
            return new int[]{13, 2};
        }
        if (item instanceof GoBoard19Item) {
            return new int[]{19, 3};
        }
        if (item instanceof GoBoard19BigItem) {
            return new int[]{19, 4};
        }
        return null;
    }

    /** 命中棋盘方块：未开局弹菜单，对局中落子；点中已有棋子的交点时弹对局菜单。 */
    private void useBoard(Player player, GoBoard board) {
        if (!board.isRunning()) {
            GoMenu.open(player, board);
            return;
        }
        int cell = board.aimCell(player);
        if (cell == 0) {
            player.sendTip("§c请将准星对准棋盘上的交叉点。");
            return;
        }
        int n = board.getN();
        if (board.isOccupied((cell - 1) / n, (cell - 1) % n)) {
            GoMenu.openInGame(player, board);
            return;
        }
        String tip = board.place(player);
        if (tip != null) {
            player.sendTip(tip);
        }
    }

    private boolean canPlace(Player player) {
        long now = System.currentTimeMillis();
        Long last = placeCooldown.get(player.getUniqueId());
        if (last != null && now - last < PLACE_COOLDOWN_MS) {
            return false;
        }
        placeCooldown.put(player.getUniqueId(), now);
        return true;
    }

    private void tryPlace(Player player, PlayerInteractEvent event, int n, int size) {
        BlockFace face = event.getFace();
        if (face == null) {
            return;
        }
        Vector3 target = event.getBlock().getSide(face);
        int bx = target.getFloorX();
        int by = target.getFloorY();
        int bz = target.getFloorZ();
        Level level = player.getLevel();

        int rotation = TabletopGameBoard.normalizeRotation((int) Math.round(player.getYaw() / 90.0));
        int px = TabletopGameBoard.axisPX(rotation);
        int pz = TabletopGameBoard.axisPZ(rotation);
        int qx = TabletopGameBoard.axisQX(rotation);
        int qz = TabletopGameBoard.axisQZ(rotation);

        // 奇数边长以点击方块为中心：区域原点回退 (size-1)/2 格；偶数取下取整，行为与五子棋一致
        int back = (size - 1) / 2;
        bx -= back * px + back * qx;
        bz -= back * pz + back * qz;

        for (int i = 0; i < size; i++) {
            for (int j = 0; j < size; j++) {
                Block b = level.getBlock(bx + i * px + j * qx, by, bz + i * pz + j * qz);
                if (!b.isAir() && !b.canBeReplaced()) {
                    player.sendTip("§c空间不足，放置棋盘需要 " + size + "x" + size + " 空地。");
                    return;
                }
            }
        }
        List<GoBoard> sameLevel = boardsByLevel.get(level);
        if (sameLevel != null) {
            for (int i = 0; i < sameLevel.size(); i++) {
                GoBoard board = sameLevel.get(i);
                if (board.getBaseY() == by && overlaps(board, bx, bz, size, rotation)) {
                    player.sendTip("§c这里已经有棋盘了。");
                    return;
                }
            }
        }

        event.setCancelled(true);
        placeBlocks(level, bx, by, bz, size, n, rotation);

        double half = (size - 1) / 2.0;
        level.addSound(new Vector3(
                bx + half * (px + qx) + 0.5,
                by + 0.5,
                bz + half * (pz + qz) + 0.5), Sound.DIG_WOOD, 1.0f, 0.8f);

        GoBoard board = new GoBoard(this, level, bx, by, bz, size, n, rotation);
        board.spawnPieces();
        boards.put(board.getKey(), board);
        indexBoard(board);
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
        player.sendTip("§a已放置 " + n + " 路围棋棋盘。");
    }

    /** 按朝向铺设 size x size 棋盘方块，position = (i + j * size) * 4 + rotation。 */
    private void placeBlocks(Level level, int bx, int by, int bz, int size, int n, int rotation) {
        int px = TabletopGameBoard.axisPX(rotation);
        int pz = TabletopGameBoard.axisPZ(rotation);
        int qx = TabletopGameBoard.axisQX(rotation);
        int qz = TabletopGameBoard.axisQZ(rotation);
        for (int i = 0; i < size; i++) {
            for (int j = 0; j < size; j++) {
                GoBoardBlock block = GoBoard.newBlock(n, size);
                block.setPosition((i + j * size) * 4 + rotation);
                level.setBlock(new Vector3(bx + i * px + j * qx, by, bz + i * pz + j * qz), block, true);
            }
        }
    }

    private static boolean overlaps(GoBoard board, int bx, int bz, int size, int rotation) {
        int[] a = footprintBounds(board.getBaseX(), board.getBaseZ(), board.getBoardSize(), board.getRotation());
        int[] b = footprintBounds(bx, bz, size, rotation);
        return a[0] <= b[1] && b[0] <= a[1] && a[2] <= b[3] && b[2] <= a[3];
    }

    private static int[] footprintBounds(int bx, int bz, int size, int rotation) {
        int px = TabletopGameBoard.axisPX(rotation);
        int pz = TabletopGameBoard.axisPZ(rotation);
        int qx = TabletopGameBoard.axisQX(rotation);
        int qz = TabletopGameBoard.axisQZ(rotation);
        int minX = Integer.MAX_VALUE;
        int maxX = Integer.MIN_VALUE;
        int minZ = Integer.MAX_VALUE;
        int maxZ = Integer.MIN_VALUE;
        for (int i = 0; i < size; i++) {
            for (int j = 0; j < size; j++) {
                int wx = bx + i * px + j * qx;
                int wz = bz + i * pz + j * qz;
                minX = Math.min(minX, wx);
                maxX = Math.max(maxX, wx);
                minZ = Math.min(minZ, wz);
                maxZ = Math.max(maxZ, wz);
            }
        }
        return new int[]{minX, maxX, minZ, maxZ};
    }

    /**
     * 棋盘方块可像橡木板一样被挖掘，但任意一处破坏成功即视作整体收回。
     * <p>
     * {@link TabletopGameManager#onBreak} 对 {@link GoBoardBlock} 已提前返回，
     * 不会抢先取消事件或重复播放音效。
     */
    @EventHandler(priority = EventPriority.HIGH, ignoreCancelled = true)
    public void onBreak(BlockBreakEvent event) {
        Block block = event.getBlock();
        if (!(block instanceof GoBoardBlock)) {
            return;
        }
        event.setCancelled(true);
        Level level = block.getLevel();
        level.addSound(
                new Vector3(block.getFloorX() + 0.5, block.getFloorY() + 0.5, block.getFloorZ() + 0.5),
                Sound.DIG_WOOD, 1.0f, 1.0f);
        GoBoard board = findBoard(level, block.getFloorX(), block.getFloorY(), block.getFloorZ());
        if (board == null) {
            return;
        }
        retract(event.getPlayer(), board,
                new Vector3(block.getFloorX() + 0.5, block.getFloorY() + 0.25, block.getFloorZ() + 0.5));
    }

    /** 右键命中棋子实体时吞掉事件：棋子没有交互，避免右键被实体抢走。 */
    @EventHandler(priority = EventPriority.HIGH)
    public void onInteractEntity(PlayerInteractEntityEvent event) {
        if (event.getEntity() instanceof GoStoneEntity) {
            event.setCancelled(true);
        }
    }

    /** 整体收回一个棋盘：延迟一 tick 移除棋子与方块，并按需掉落棋盘物品。 */
    private void retract(Player player, GoBoard board, Vector3 dropAt) {
        boolean drop = !player.isCreative();
        Level level = board.getLevel();
        int n = board.getN();
        int size = board.getBoardSize();
        Server.getInstance().getScheduler().scheduleDelayedTask(plugin, () -> {
            if (boards.remove(board.getKey()) == null) {
                return;
            }
            unindexBoard(board);
            board.remove();
            markDirty();
            if (drop) {
                level.dropItem(dropAt, dropItemFor(n, size));
            }
        }, 1);
    }

    private static Item dropItemFor(int n, int size) {
        if (n == 9) {
            return new GoBoard9Item();
        }
        if (n == 13) {
            return new GoBoard13Item();
        }
        return size >= 4 ? new GoBoard19BigItem() : new GoBoard19Item();
    }

    @EventHandler
    public void onQuit(PlayerQuitEvent event) {
        UUID id = event.getPlayer().getUniqueId();
        placeCooldown.remove(id);
        hoverTick.remove(id);
        for (GoBoard board : boards.values()) {
            if (board.isSeated(id)) {
                board.leave(id);
            } else {
                board.releaseMenu(id);
            }
        }
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onMove(PlayerMoveEvent event) {
        updateHover(event.getPlayer());
    }

    private boolean claimHover(Player player) {
        int now = Server.getInstance().getTick();
        Integer last = hoverTick.get(player.getUniqueId());
        if (last != null && last == now) {
            return false;
        }
        hoverTick.put(player.getUniqueId(), now);
        return true;
    }

    private void updateHover(Player player) {
        List<GoBoard> list = boardsByLevel.get(player.getLevel());
        if (list == null || list.isEmpty()) {
            return;
        }
        if (!claimHover(player)) {
            return;
        }
        for (int i = 0; i < list.size(); i++) {
            GoBoard board = list.get(i);
            if (board.isRunning() && board.inRange(player)) {
                board.updateHover(player);
            }
        }
    }

    public void runLater(Runnable action) {
        runLater(action, 1);
    }

    public void runLater(Runnable action, int ticks) {
        Server.getInstance().getScheduler().scheduleDelayedTask(plugin, action, ticks);
    }

    public void reopenMenu(Player player, GoBoard board) {
        runLater(() -> GoMenu.reopen(player, board));
    }

    public void refreshSeatMenus(GoBoard board) {
        if (board.isRunning()) {
            return;
        }
        for (UUID id : new ArrayList<>(board.getSeats())) {
            Player p = Server.getInstance().getPlayer(id).orElse(null);
            if (p == null) {
                continue;
            }
            GoMenu.closeCurrentForm(p);
            reopenMenu(p, board);
        }
    }

    public void closeSeatMenus(GoBoard board) {
        for (UUID id : new ArrayList<>(board.getSeats())) {
            Player p = Server.getInstance().getPlayer(id).orElse(null);
            if (p != null) {
                GoMenu.closeCurrentForm(p);
            }
        }
    }

    /** 周期任务：关卡就绪后恢复存档；棋子实体缺失且玩家回到范围时按需重建。 */
    public void tick() {
        if (loadPending && !Server.getInstance().getLevels().isEmpty()) {
            loadPending = false;
            load();
        }
        if (dirty) {
            dirty = false;
            save();
        }
        for (Map.Entry<Level, List<GoBoard>> entry : boardsByLevel.entrySet()) {
            boolean levelEmpty = entry.getKey().getPlayers().isEmpty();
            List<GoBoard> levelBoards = entry.getValue();
            for (int b = 0; b < levelBoards.size(); b++) {
                GoBoard board = levelBoards.get(b);
                if (!levelEmpty) {
                    if (board.isPiecesMissing() && board.hasPlayerInRange()) {
                        board.spawnPieces();
                    }
                    UUID hoverId = board.hoverPlayerId();
                    if (hoverId != null) {
                        Player hover = Server.getInstance().getPlayer(hoverId).orElse(null);
                        if (hover != null && board.inRange(hover) && claimHover(hover)) {
                            board.updateHover(hover);
                        }
                    }
                }
                board.collectLeftPlayers(leftScratch);
                for (int i = 0; i < leftScratch.size(); i++) {
                    UUID id = leftScratch.get(i);
                    board.leave(id);
                    Player p = Server.getInstance().getPlayer(id).orElse(null);
                    if (p != null) {
                        p.sendTip("§e你已离开棋盘范围，自动退出棋局。");
                    }
                }
                board.tickMenuHolder();
                // 轮到机器人：异步计算落点，避免阻塞主线程
                if (!levelEmpty && board.isAiTurn() && board.beginThinking()) {
                    scheduleAiMove(board);
                }
            }
        }
    }

    /** 派发一次机器人落子：在线程池中异步计算落点，再回到主线程落子。 */
    private void scheduleAiMove(GoBoard board) {
        int[] snapshot = board.copyGrid();
        int n = board.getN();
        int toMove = board.getTurn();
        int level = board.getAiLevel();
        int ko = board.koIndex();
        int passes = board.getPasses();
        double komi = board.getKomi();
        Server.getInstance().getScheduler().scheduleTask(plugin, () -> {
            int[] move = GoAi.bestMove(snapshot, n, toMove, level, ko, passes, komi);
            Server.getInstance().getScheduler().scheduleTask(plugin, () -> {
                board.finishThinking();
                // 兜底：机器人着法被拒时不能再派发，否则本轮会无限重算并把线程池打满
                if (!board.aiApply(move)) {
                    board.abort("机器人无法落子，本局结束（可稍后「继承残局」继续）。");
                }
            }, false);
        }, true);
    }

    /**
     * 一个棋盘的 YAML 记录：
     * 世界、坐标、朝向、路数、方块边长、turn、started、komi、handicap、passes、盘面。
     */
    private static Map<String, Object> toMap(GoBoard board) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("world", board.getLevel().getName());
        m.put("x", board.getBaseX());
        m.put("y", board.getBaseY());
        m.put("z", board.getBaseZ());
        m.put("rotation", board.getRotation());
        m.put("n", board.getN());
        m.put("size", board.getBoardSize());
        m.put("turn", board.getTurn());
        m.put("started", board.hasStarted() ? 1 : 0);
        m.put("komi", board.getKomi());
        m.put("handicap", board.getHandicap());
        m.put("passes", board.getPasses());
        m.put("grid", board.exportGrid());
        return m;
    }

    /** YAML 记录还原为 {@link #restoreBoard(String[])} 使用的纯数据（{@code G|世界|X|Y|Z|朝向|路数|边长|turn|started|komi|handicap|passes|盘面}）。 */
    private static String[] toParts(Map<?, ?> m) {
        return new String[]{"G",
                BoardStorage.stringValue(m, "world", ""),
                String.valueOf(BoardStorage.intValue(m, "x", 0)),
                String.valueOf(BoardStorage.intValue(m, "y", 0)),
                String.valueOf(BoardStorage.intValue(m, "z", 0)),
                String.valueOf(BoardStorage.intValue(m, "rotation", 0)),
                String.valueOf(BoardStorage.intValue(m, "n", 9)),
                String.valueOf(BoardStorage.intValue(m, "size", 2)),
                String.valueOf(BoardStorage.intValue(m, "turn", GoBoard.BLACK)),
                String.valueOf(BoardStorage.intValue(m, "started", 0)),
                String.valueOf(BoardStorage.doubleValue(m, "komi", GoBoard.DEFAULT_KOMI)),
                String.valueOf(BoardStorage.intValue(m, "handicap", 0)),
                String.valueOf(BoardStorage.intValue(m, "passes", 0)),
                BoardStorage.stringValue(m, "grid", "")};
    }

    /** 存档文件（YAML）：根节点 {@code boards} 为棋盘记录列表。 */
    private File storageFile() {
        return BoardStorage.file(plugin, STORAGE_FILE);
    }

    /** 旧版 .txt 存档，仅用于迁移读取。 */
    private File legacyFile() {
        return BoardStorage.file(plugin, LEGACY_STORAGE_FILE);
    }

    private void save() {
        if (!restored || saveExecutor.isShutdown()) {
            return;
        }
        File file = storageFile();
        saveExecutor.execute(() -> writeYaml(file, collect()));
    }

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
                plugin.getLogger().warning("等待围棋棋盘数据写入超时。");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    /** 主线程拼装当前全部棋盘的 YAML 数据结构。 */
    private Map<String, Object> collect() {
        List<Map<String, Object>> boardsData = new ArrayList<>(boards.size());
        for (GoBoard board : boards.values()) {
            boardsData.add(toMap(board));
        }
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("boards", boardsData);
        return root;
    }

    private void writeYaml(File file, Object data) {
        try {
            Files.writeString(file.toPath(), BoardStorage.dump(data), StandardCharsets.UTF_8);
        } catch (IOException e) {
            plugin.getLogger().warning("保存围棋棋盘数据失败：" + e.getMessage());
        }
    }

    public void load() {
        File file = storageFile();
        File legacy = legacyFile();
        Server.getInstance().getScheduler().scheduleTask(plugin, () -> {
            // 仅有旧 .txt 存档时走迁移：读旧格式，加载完成后落盘新 YAML 并删除旧文件
            boolean migrate = !file.isFile() && legacy.isFile();
            List<String[]> saved = parse(file);
            Server.getInstance().getScheduler().scheduleTask(plugin, () -> {
                for (String[] parts : saved) {
                    restoreBoard(parts);
                }
                restored = true;
                if (!saved.isEmpty()) {
                    plugin.getLogger().info("已从磁盘恢复 " + boards.size() + " 个围棋棋盘。");
                }
                if (migrate && !saved.isEmpty()) {
                    save();
                    saveExecutor.execute(() -> {
                        if (legacy.delete()) {
                            plugin.getLogger().info("已将旧存档 " + LEGACY_STORAGE_FILE
                                    + " 迁移为 " + STORAGE_FILE + " 并删除旧文件。");
                        }
                    });
                }
            }, false);
        }, true);
    }

    /** 读取并解析存档为纯数据（不触碰世界，可在异步线程执行）。新档为 YAML，缺失时回退旧 .txt。 */
    private List<String[]> parse(File file) {
        List<String[]> saved = new ArrayList<>();
        if (!file.isFile()) {
            return parseLegacy(legacyFile());
        }
        Object data = BoardStorage.load(file);
        if (!(data instanceof Map<?, ?> root) || !(root.get("boards") instanceof List<?> list)) {
            if (data == null) {
                plugin.getLogger().warning("读取围棋棋盘数据失败（YAML 解析失败或文件不可读）：" + file.getName());
            }
            return saved;
        }
        for (Object item : list) {
            if (item instanceof Map<?, ?> board) {
                saved.add(toParts(board));
            }
        }
        return saved;
    }

    /** 读取旧版 {@code go_boards.txt}（竖线分隔）为纯数据，仅供迁移使用。 */
    private List<String[]> parseLegacy(File file) {
        List<String[]> saved = new ArrayList<>();
        if (!file.isFile()) {
            return saved;
        }
        List<String> lines;
        try {
            lines = Files.readAllLines(file.toPath(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            plugin.getLogger().warning("读取围棋棋盘数据失败：" + e.getMessage());
            return saved;
        }
        for (String line : lines) {
            if (line.isBlank()) {
                continue;
            }
            String[] parts = line.split("\\|", -1);
            if ("G".equals(parts[0]) && parts.length >= 14) {
                saved.add(parts);
            }
        }
        return saved;
    }

    private void restoreBoard(String[] parts) {
        Level level = Server.getInstance().getLevelByName(parts[1]);
        if (level == null) {
            plugin.getLogger().warning("围棋棋盘所在世界未加载，跳过：" + parts[1]);
            return;
        }
        int x = parseInt(parts[2], 0);
        int y = parseInt(parts[3], 0);
        int z = parseInt(parts[4], 0);
        int rotation = parseInt(parts[5], 0);
        int n = parseInt(parts[6], 9);
        int size = parseInt(parts[7], 2);
        placeBlocks(level, x, y, z, size, n, rotation);
        GoBoard board = new GoBoard(this, level, x, y, z, size, n, rotation);
        board.importState(parseInt(parts[8], GoBoard.BLACK), parseInt(parts[9], 0) != 0,
                parseDouble(parts[10], GoBoard.DEFAULT_KOMI), parseInt(parts[11], 0),
                parseInt(parts[12], 0), parts[13]);
        board.spawnPieces();
        boards.put(board.getKey(), board);
        indexBoard(board);
    }

    private static int parseInt(String value, int fallback) {
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException e) {
            return fallback;
        }
    }

    private static double parseDouble(String value, double fallback) {
        try {
            return Double.parseDouble(value);
        } catch (NumberFormatException e) {
            return fallback;
        }
    }
}
