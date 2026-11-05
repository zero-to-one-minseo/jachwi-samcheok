#!/bin/sh
# 프로젝트 폴더의 원본 문서를 app/docs/로 다시 복사한다. 원본은 프로젝트 폴더에 있고, 이 폴더는 팀 공유용 사본이다.
set -e
cd "$(dirname "$0")/.."
ROOT=".."
cp "$ROOT/메인_현황판.md" "$ROOT/기획_자취계약서.md" "$ROOT/설계_구현방법.md" "$ROOT/설계_시세현황판.md" \
   "$ROOT/사양서_조립.md" "$ROOT/기술_확인.md" "$ROOT/법_근거_검증.md" "$ROOT/수상작_조사.md" docs/
cp "$ROOT/Codex/해커톤_개회식_안내정리.md" "$ROOT/Codex/수상작_또박_심층조사.md" docs/
cp "$ROOT/Claude/에타_조사/에타_자취방_정리.md" docs/
cp "$ROOT/Claude/자취방_공개정보_조사/공공데이터_정리.md" docs/
cp "$ROOT/Claude/자취방_공개정보_조사/README.md" docs/웹조사_정리.md
echo "docs 복사 완료: $(ls docs | wc -l | tr -d ' ')개"
