/**
 * tabBar 图标转换脚本：SVG → PNG
 *
 * 微信小程序 tabBar 仅支持 PNG/JPG/JPEG（建议 81×81px、单图 ≤40KB），不支持 SVG。
 * 本脚本把 src/assets/tabbar/*.svg 原样栅格化为 81×81 透明背景 PNG（同名 .png），
 * 颜色与描边均来自 SVG 本身（普通态 #999999 / 选中态 #165dff），外观零变化。
 *
 * 用法：node scripts/convert-tabbar-icons.mjs
 * 依赖：@resvg/resvg-js（预编译原生包，Windows 免编译）
 */
import { readdirSync, readFileSync, writeFileSync, statSync } from 'node:fs'
import { join, basename, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { Resvg } from '@resvg/resvg-js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const SRC_DIR = join(__dirname, '..', 'src', 'assets', 'tabbar')
const SIZE = 81 // 微信官方推荐尺寸；单图上限 40KB

const svgs = readdirSync(SRC_DIR).filter((f) => f.toLowerCase().endsWith('.svg'))
if (svgs.length === 0) {
  console.error(`未在 ${SRC_DIR} 找到任何 .svg 文件`)
  process.exit(1)
}

let failed = 0
for (const file of svgs) {
  const svgPath = join(SRC_DIR, file)
  const pngPath = join(SRC_DIR, file.replace(/\.svg$/i, '.png'))
  try {
    const resvg = new Resvg(readFileSync(svgPath, 'utf8'), {
      fitTo: { mode: 'width', value: SIZE },
      background: 'rgba(0,0,0,0)', // 透明背景
    })
    const png = resvg.render().asPng()
    writeFileSync(pngPath, png)
    const kb = (statSync(pngPath).size / 1024).toFixed(1)
    const ok = statSync(pngPath).size <= 40 * 1024 ? 'OK' : '超限!'
    console.log(`${basename(pngPath).padEnd(24)} ${SIZE}x${SIZE}  ${kb}KB  ${ok}`)
    if (ok !== 'OK') failed++
  } catch (err) {
    console.error(`${file} 转换失败: ${err.message}`)
    failed++
  }
}

console.log(`\n完成：${svgs.length - failed}/${svgs.length} 张 PNG 已生成于 src/assets/tabbar/`)
process.exit(failed ? 1 : 0)
