import com.tabletopgame.game.UnoDeck;
import com.tabletopgame.game.UnoGame;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;

/**
 * 野牌（Wild / Wild+4）选色流程的脱机复现。
 * <p>
 * 按 UnoTable 的真实点击顺序走：
 * <ol>
 *   <li>玩家在手里点中野牌，点「出牌」；</li>
 *   <li>点「出牌」时先过 {@link UnoGame#checkPlay}；不过 → 提示 + 原地不动（不进选色态）；</li>
 *   <li>过了才进选色态（此时 game 没被改动），再点某一种颜色 → {@code game.play(seat, 野牌, 颜色)}。</li>
 * </ol>
 * 关键不变式：**checkPlay 通过 ⟹ play 一定成功**。否则玩家会卡在只有四个颜色按钮的
 * 选色界面里（那一组没有取消 / 抽牌 / 跳过），只能等 45 秒超时代打 —— 这就是
 * 「两张万能牌出牌后选不了颜色卡住」的成因。
 */
public final class WildCheck {

    public static void main(String[] args) {
        Map<String, Integer> refused = new HashMap<>();   // 被 checkPlay 拦下（正确行为）
        Map<String, Integer> okByKind = new HashMap<>();  // 进选色态后成功出牌
        Map<String, Integer> stuck = new HashMap<>();     // 进选色态后出牌失败 = 仍会卡死
        int attempts = 0;
        int noEscape = 0;

        for (int seed = 1; seed <= 400; seed++) {
            UnoGame game = new UnoGame(4, new Random(seed));
            if (!setup(game)) {
                continue;
            }
            for (int step = 0; step < 400 && game.phase() == UnoGame.PHASE_PLAYING; step++) {
                int seat = game.currentSeat();
                if (game.isStartColorPending()) {
                    if (game.chooseStartColor(seat, 0) != null) {
                        break;
                    }
                    continue;
                }
                List<Integer> hand = game.hand(seat);

                // 复刻 doPlayButton：它从**整只手牌**里拿牌（不预筛 playable）
                int wild = -1;
                for (int id : hand) {
                    if (UnoDeck.isWild(id)) {
                        wild = id;
                        break;
                    }
                }
                if (wild >= 0 && !game.hasDrawn()) {
                    attempts++;
                    String kind = UnoDeck.kind(wild) == UnoDeck.KIND_WILD ? "Wild" : "Wild+4";
                    String why = game.checkPlay(seat, wild);
                    if (why != null) {
                        refused.merge(kind + " -> " + why, 1, Integer::sum);
                        // 被拦下后 UI 留在原按钮组：必须能抽牌自救
                        if (game.draw(seat) != null) {
                            noEscape++;
                        }
                        if (game.hasDrawn()) {
                            game.pass(seat);
                        }
                        continue;
                    }
                    // 进选色态 → 点红色
                    String err = game.play(seat, wild, 0);
                    if (err == null) {
                        okByKind.merge(kind, 1, Integer::sum);
                    } else {
                        stuck.merge(kind + " -> " + err, 1, Integer::sum);
                    }
                    continue;
                }

                // 「摸到野牌」路径：摸牌后只能出刚摸到的那张
                if (!game.hasDrawn()) {
                    if (game.draw(seat) != null) {
                        break;
                    }
                }
                int drawn = game.drawnCard();
                if (drawn >= 0 && UnoDeck.isWild(drawn)) {
                    attempts++;
                    String kind = "摸到的" + (UnoDeck.kind(drawn) == UnoDeck.KIND_WILD ? "Wild" : "Wild+4");
                    String why = game.checkPlay(seat, drawn);
                    if (why != null) {
                        refused.merge(kind + " -> " + why, 1, Integer::sum);
                        if (game.pass(seat) != null) {
                            noEscape++;
                        }
                        continue;
                    }
                    String err = game.play(seat, drawn, 0);
                    if (err == null) {
                        okByKind.merge(kind, 1, Integer::sum);
                    } else {
                        stuck.merge(kind + " -> " + err, 1, Integer::sum);
                    }
                    continue;
                }
                if (game.hasDrawn()) {
                    game.pass(seat);
                } else {
                    game.draw(seat);
                    if (game.hasDrawn()) {
                        game.pass(seat);
                    }
                }
            }
        }

        System.out.println("野牌「点出牌」次数：" + attempts);
        System.out.println("进选色态并成功出牌：" + okByKind);
        System.out.println("被 checkPlay 提前拦下（= 不进选色态、不会卡死）：");
        if (refused.isEmpty()) {
            System.out.println("  （无）");
        }
        for (Map.Entry<String, Integer> e : refused.entrySet()) {
            System.out.println("  " + e.getValue() + " 次  " + e.getKey());
        }
        System.out.println("拦下后连「抽牌/跳过」都做不了的次数：" + noEscape + "   （必须为 0）");
        System.out.println("通过 checkPlay 却仍然出牌失败（= 仍会卡死）："
                + (stuck.isEmpty() ? "0 类 ✓" : stuck.toString()));
    }

    /** 定庄 → 发牌。 */
    private static boolean setup(UnoGame game) {
        for (int guard = 0; guard < 64; guard++) {
            int r = -1;
            for (int s = 0; s < game.players(); s++) {
                r = game.drawForDealer(s);
                if (r == UnoGame.DRAW_TIE_REDRAW) {
                    break;
                }
            }
            if (r == UnoGame.DRAW_TIE_REDRAW) {
                continue;
            }
            if (r == UnoGame.DRAW_DEALER_DECIDED) {
                break;
            }
        }
        if (game.dealerSeat() < 0) {
            return false;
        }
        return game.deal() == null;
    }
}
