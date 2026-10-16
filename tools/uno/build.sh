#!/usr/bin/env bash
# 编译 TabletopGamePlugin（含 UNO）。本机无 maven，直接用 javac + .m2 里的依赖 jar。
# 用法：bash tools/uno/build.sh          # 只编译
#       bash tools/uno/build.sh jar      # 编译并打 jar 到 target/
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
JDK="${JDK17:-D:/JDK17}"
JAVAC="$JDK/bin/javac.exe"
JAR="$JDK/bin/jar.exe"
M2="$HOME/.m2/repository"

# git-bash 路径 -> Windows 路径，javac/jar 是原生程序，只认后者
win() { cygpath -w "$1"; }

NUKKIT="$M2/cn/nukkit/Nukkit/MOT-SNAPSHOT/Nukkit-MOT-SNAPSHOT.jar"
OKAERI_CORE="$M2/eu/okaeri/okaeri-configs-core/6.1.0-beta.1/okaeri-configs-core-6.1.0-beta.1.jar"
OKAERI_YAML="$M2/eu/okaeri/okaeri-configs-yaml-snakeyaml/6.1.0-beta.1/okaeri-configs-yaml-snakeyaml-6.1.0-beta.1.jar"

for f in "$NUKKIT" "$OKAERI_CORE" "$OKAERI_YAML"; do
  [ -f "$f" ] || { echo "缺少依赖：$f" >&2; exit 1; }
done

CP="$(win "$NUKKIT");$(win "$OKAERI_CORE");$(win "$OKAERI_YAML")"

cd "$REPO"
rm -rf target/classes
mkdir -p target/classes

# 相对路径写进 argfile：javac 在 Windows 下接受正斜杠相对路径
find src/main/java -name '*.java' > target/_sources.txt
echo "源文件数：$(wc -l < target/_sources.txt)"

"$JAVAC" -encoding UTF-8 -source 17 -target 17 -nowarn \
  -cp "$CP" -d target/classes @target/_sources.txt

cp -r src/main/resources/. target/classes/
echo "编译完成 -> $REPO/target/classes"

if [ "${1:-}" = "jar" ]; then
  rm -f target/TabletopGame-1.0.0-SNAPSHOT.jar
  "$JAR" --create --file target/TabletopGame-1.0.0-SNAPSHOT.jar -C target/classes .
  echo "打包完成 -> $REPO/target/TabletopGame-1.0.0-SNAPSHOT.jar"
fi
