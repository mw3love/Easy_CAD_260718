// 시험 전 — 임시 데이터 폴더를 비운다(지난 시험의 칠판·비밀번호 파일이 남지 않게)
import { mkdirSync, readdirSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { DATA } from './helpers.js'

export default function globalSetup() {
  mkdirSync(DATA, { recursive: true })
  for (const f of readdirSync(DATA)) rmSync(join(DATA, f), { recursive: true, force: true })
}
