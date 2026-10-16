// -*- coding: utf-8 -*-
//
// UNO 规则引擎对局模拟器（纯逻辑，不依赖 Nukkit）。
//
// 目的：在写服务端交互层之后，仍然能用「随机对局 + 全量不变量」把 UnoGame / UnoDeck / UnoAi
// 的规则漏洞一次跑出来 —— 这类错误在客户端只表现为「牌数不对 / 该摸牌没摸 / 回合跳错人」，
// 服务端不报错，靠人眼盯着玩很难发现。
//
// 校验的不变量：
//   1. 牌张守恒：全部手牌 + 摸牌堆 + 弃牌堆 = 108，且 108 个牌 id 恰好各出现一次
//      （UNO 的牌 id 是物理身份，两张「红 5」是两个不同 id，所以「不重复」是强约束）；
//   2. playableCards() 返回的牌必定在本人手上；
//   3. 摸牌后 playableCards() 只可能是「刚摸到的那张」；
//   4. +2 / +4 的受害者确实多摸了 2 / 4 张，且被跳过（下一手不是他）；
//   5. 跳过 → 下家被跳；反转 → 方向取反（2 人局等同跳过，本人继续）；
//   6. Wild+4：手上还有当前颜色时不可出；
//   7. 局末 handPoints() 与手牌分值一致；有人出完则 winnerSeat 有效。
//
// 用法（无需 Nukkit）：
//   javac -d <tmp> UnoDeck.java UnoGame.java UnoAi.java SimUno.java
//   java -cp <tmp> SimUno [每组合局数]

import com.tabletopgame.ai.UnoAi;
import com.tabletopgame.game.UnoDeck;
import com.tabletopgame.game.UnoGame;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Random;
import java.util.Set;

public final class SimUno {

    private static int failures;

    public static void main(String[] args) {
        int perCombo = args.length > 0 ? Integer.parseInt(args[0]) : 400;
        long seed0 = 20261013L;
        int games = 0;
        for (int players = 2; players <= 4; players++) {
            for (int levels = 0; levels < 3; levels++) {
                Random seed = new Random(seed0 + players * 31L + levels);
                for (int i = 0; i < perCombo; i++) {
                    playOne(players, levels, new Random(seed.nextLong()));
                    games++;
                }
            }
        }
        System.out.println("模拟对局：" + games + " 局");
        System.out.println("total problems : " + failures);
        if (failures > 0) {
            System.exit(1);
        }
    }

    /** 打完整一局：定庄 → 发牌 → 用 AI 走到底，全程校验不变量。 */
    private static void playOne(int players, int levelMode, Random random) {
        String tag = players + "人/档" + levelMode;
        UnoAi[] ai = new UnoAi[players];
        for (int s = 0; s < players; s++) {
            ai[s] = new UnoAi(levelMode, random);
        }
        UnoGame game = new UnoGame(players, random);

        // ---- 定庄 ----
        int guard = 0;
        while (game.phase() == UnoGame.PHASE_DEALER_DRAW && guard++ < 64) {
            boolean tie = false;
            for (int s = 0; s < players; s++) {
                int r = game.drawForDealer(s);
                if (r < 0) {
                    fail(tag, "drawForDealer 返回 -1（seat=" + s + "）");
                    return;
                }
                if (r == UnoGame.DRAW_TIE_REDRAW) {
                    tie = true;
                    break;
                }
                if (r == UnoGame.DRAW_DEALER_DECIDED) {
                    break;
                }
            }
            if (tie) {
                continue;
            }
            break;
        }
        if (game.dealerSeat() < 0) {
            fail(tag, "定庄未产生庄家");
            return;
        }
        if (game.phase() != UnoGame.PHASE_DEALER_DRAW) {
            fail(tag, "定庄阶段异常结束");
            return;
        }
        int dealer = game.dealerSeat();
        if (game.deal() != null) {
            fail(tag, "发牌失败");
            return;
        }

        // 先手 = 庄家左手边；但起始牌的特效是「施加在先手身上」的（官方规则），
        // 因此生效后的当前座位要按起始牌类型换算，不能直接断言 == 庄家左手边。
        int first = Math.floorMod(dealer + 1, players);
        int top = game.topCard();
        int expectSeat;
        switch (UnoDeck.kind(top)) {
            // 起始「跳过」/「+2」：先手被跳过 → 本轮交给再下一家
            case UnoDeck.KIND_SKIP, UnoDeck.KIND_DRAW_TWO -> expectSeat = Math.floorMod(first + 1, players);
            // 起始「反转」：多人局由庄家先出（方向取反）；2 人局等同跳过（先手被跳过）
            case UnoDeck.KIND_REVERSE -> expectSeat = players == 2
                    ? Math.floorMod(first + 1, players) : dealer;
            default -> expectSeat = first;
        }
        if (game.currentSeat() != expectSeat) {
            fail(tag, "起始牌 " + UnoDeck.name(top) + " 后座位应为 " + expectSeat
                    + "，实际 " + game.currentSeat());
        }
        // 起手张数：每人 7 张，起始「+2」会让先手多 2 张
        int expectCards = UnoDeck.HAND_SIZE * players
                + (UnoDeck.kind(top) == UnoDeck.KIND_DRAW_TWO ? 2 : 0);
        int actualCards = 0;
        for (int s = 0; s < players; s++) {
            actualCards += game.handSize(s);
            if (game.handSize(s) < UnoDeck.HAND_SIZE) {
                fail(tag, "起手少于 7 张（seat=" + s + " → " + game.handSize(s) + "）");
            }
        }
        if (actualCards != expectCards) {
            fail(tag, "起手总张数应为 " + expectCards + "，实际 " + actualCards);
        }
        checkConservation(tag, game);

        // ---- 对局 ----
        int steps = 0;
        while (game.phase() == UnoGame.PHASE_PLAYING && steps++ < 20000) {
            int seat = game.currentSeat();
            if (seat < 0 || seat >= players) {
                fail(tag, "currentSeat 越界：" + seat);
                return;
            }
            if (game.isStartColorPending()) {
                int color = ai[seat].chooseColor(game.hand(seat));
                if (color < 0 || color >= UnoDeck.COLOR_COUNT) {
                    fail(tag, "起始选色越界：" + color);
                    return;
                }
                if (game.chooseStartColor(seat, color) != null) {
                    fail(tag, "起始选色被拒");
                    return;
                }
                continue;
            }

            List<Integer> handBefore = new ArrayList<>(game.hand(seat));
            List<Integer> playable = game.playableCards(seat);
            for (int id : playable) {
                if (!handBefore.contains(id)) {
                    fail(tag, "playableCards 返回了不在手上的牌：" + id);
                }
            }
            if (game.hasDrawn() && playable.size() > 1) {
                fail(tag, "摸牌后可出的牌多于一张：" + playable);
            }
            if (game.hasDrawn() && !playable.isEmpty() && !playable.contains(game.drawnCard())) {
                fail(tag, "摸牌后可出的牌不是刚摸到的那张");
            }

            if (game.hasDrawn()) {
                int drawn = game.drawnCard();
                boolean legal = playable.contains(drawn);
                if (ai[seat].shouldPlayDrawn(drawn, handBefore, legal)) {
                    int color = UnoDeck.isWild(drawn) ? ai[seat].chooseColor(handBefore) : -1;
                    if (game.play(seat, drawn, color) != null) {
                        fail(tag, "摸牌后出牌被拒：" + drawn);
                        return;
                    }
                } else {
                    int next = step(game, seat);
                    if (game.pass(seat) != null) {
                        fail(tag, "摸牌后跳过被拒");
                        return;
                    }
                    if (game.phase() == UnoGame.PHASE_PLAYING && game.currentSeat() != next) {
                        fail(tag, "跳过后未交给下一家");
                    }
                }
                checkConservation(tag, game);
                continue;
            }

            int nextSeat = Math.floorMod(seat + game.direction(), players);
            // 手上还有当前颜色时不允许出 Wild+4
            for (int id : playable) {
                if (UnoDeck.kind(id) == UnoDeck.KIND_WILD_DRAW_FOUR) {
                    for (int c : handBefore) {
                        if (!UnoDeck.isWild(c) && UnoDeck.color(c) == game.activeColor()) {
                            fail(tag, "手上还有当前颜色却把 Wild+4 列为可出");
                            return;
                        }
                    }
                }
            }

            int dirBefore = game.direction();
            int handBeforeSize = game.handSize(seat);
            UnoAi.Decision d = ai[seat].decide(handBefore, playable, game.activeColor(),
                    game.handSize(nextSeat));
            if (d.draw()) {
                if (game.draw(seat) != null) {
                    fail(tag, "主动摸牌被拒");
                    return;
                }
                if (game.handSize(seat) != handBeforeSize + 1) {
                    fail(tag, "摸牌后手牌数没 +1");
                }
                checkConservation(tag, game);
                continue;
            }

            int card = d.cardId();
            if (!handBefore.contains(card)) {
                fail(tag, "AI 决定出的牌不在手上：" + card);
                return;
            }
            int kind = UnoDeck.kind(card);
            int amount = UnoDeck.drawAmount(card);
            int victim = nextSeat;
            int victimBefore = game.handSize(victim);
            if (game.play(seat, card, d.chosenColor()) != null) {
                fail(tag, "AI 出牌被拒：" + UnoDeck.name(card));
                return;
            }
            // +2 / +4：受害者确实多摸，且被跳过
            if (amount > 0 && game.phase() == UnoGame.PHASE_PLAYING) {
                if (game.handSize(victim) != victimBefore + amount) {
                    fail(tag, UnoDeck.name(card) + " 受害者摸牌数不对：期望 "
                            + (victimBefore + amount) + "，实际 " + game.handSize(victim));
                }
                if (game.currentSeat() == victim) {
                    fail(tag, UnoDeck.name(card) + " 的受害者没有被跳过");
                }
            }
            if (kind == UnoDeck.KIND_SKIP && game.phase() == UnoGame.PHASE_PLAYING) {
                if (game.currentSeat() == victim) {
                    fail(tag, "跳过牌没有跳过下家");
                }
            }
            if (kind == UnoDeck.KIND_REVERSE && game.phase() == UnoGame.PHASE_PLAYING) {
                if (players == 2) {
                    if (game.direction() != dirBefore) {
                        fail(tag, "2 人局反转不应改变方向");
                    }
                    if (game.currentSeat() != seat) {
                        fail(tag, "2 人局反转应等同跳过（自己继续出）");
                    }
                } else {
                    if (game.direction() == dirBefore) {
                        fail(tag, "反转牌没有改变方向");
                    }
                }
            }
            if (game.phase() == UnoGame.PHASE_PLAYING && game.handSize(seat) == 0) {
                fail(tag, "手牌为空却没有结束本局");
            }
            checkConservation(tag, game);
        }

        if (steps >= 20000) {
            fail(tag, "对局未在 20000 步内结束（疑似死循环）");
            return;
        }
        if (game.phase() != UnoGame.PHASE_FINISHED) {
            fail(tag, "对局结束阶段异常：" + game.phase());
            return;
        }
        // 局末：有人出完则赢家手牌为空；分值与手牌一致
        if (!game.exhausted()) {
            int w = game.winnerSeat();
            if (w < 0 || w >= players) {
                fail(tag, "赢家座位无效：" + w);
            } else if (game.handSize(w) != 0) {
                fail(tag, "赢家手上还有 " + game.handSize(w) + " 张牌");
            }
        }
        for (int s = 0; s < players; s++) {
            int sum = 0;
            for (int id : game.hand(s)) {
                sum += UnoDeck.points(id);
            }
            if (sum != game.handPoints(s)) {
                fail(tag, "手牌分值不一致（seat=" + s + "）");
            }
        }
    }

    /** 预演一次推进后的座位（不改状态）。 */
    private static int step(UnoGame game, int seat) {
        return Math.floorMod(seat + game.direction(), game.players());
    }

    /** 牌张守恒 + 手牌里 108 个牌 id 不重不漏。 */
    private static void checkConservation(String tag, UnoGame game) {
        Set<Integer> seen = new HashSet<>();
        int hands = 0;
        for (int s = 0; s < game.players(); s++) {
            hands += game.handSize(s);
            for (int id : game.hand(s)) {
                if (id < 0 || id >= UnoDeck.SIZE) {
                    fail(tag, "手牌 id 越界：" + id);
                    return;
                }
                if (!seen.add(id)) {
                    fail(tag, "同一张物理牌出现在多个手牌位置：" + id);
                    return;
                }
            }
        }
        int drawPile = game.drawPileSize();
        int discard = game.discardSize();
        if (hands + drawPile + discard != UnoDeck.SIZE) {
            fail(tag, "牌张守恒被破坏：手牌 " + hands + " + 摸牌堆 " + drawPile
                    + " + 弃牌堆 " + discard + " ≠ " + UnoDeck.SIZE);
        }
    }

    private static void fail(String tag, String message) {
        failures++;
        if (failures <= 20) {
            System.out.println("  FAIL [" + tag + "] " + message);
        }
    }
}
