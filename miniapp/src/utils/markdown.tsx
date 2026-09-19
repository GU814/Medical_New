import React from 'react';
import { View, Text } from '@tarojs/components';

/**
 * 轻量 Markdown 渲染器(用于报告展示)
 * 支持:标题(#/##/###)、加粗(**)、无序列表(-/*)、有序列表(1.)、分隔线(---)、段落
 * 沿用现有 chat.js 的轻量规则,避免引入重量级依赖
 */

interface MarkdownProps {
  source: string
  className?: string
}

interface Block {
  type: 'h1' | 'h2' | 'h3' | 'p' | 'ul' | 'ol' | 'hr'
  items?: string[] // 列表项
  text?: string
}

function parse(md: string): Block[] {
  const lines = md.split('\n')
  const blocks: Block[] = []
  let i = 0
  let para: string[] = []
  let list: { type: 'ul' | 'ol'; items: string[] } | null = null

  const flushPara = () => {
    if (para.length) {
      blocks.push({ type: 'p', text: para.join(' ').trim() })
      para = []
    }
  }
  const flushList = () => {
    if (list) {
      blocks.push({ type: list.type, items: list.items })
      list = null
    }
  }

  while (i < lines.length) {
    const line = lines[i]
    const trimmed = line.trim()

    if (trimmed === '') {
      flushPara()
      flushList()
      i++
      continue
    }

    if (/^---+$/.test(trimmed)) {
      flushPara()
      flushList()
      blocks.push({ type: 'hr' })
      i++
      continue
    }

    const h1 = trimmed.match(/^#\s+(.*)/)
    const h2 = trimmed.match(/^##\s+(.*)/)
    const h3 = trimmed.match(/^###\s+(.*)/)
    if (h1 || h2 || h3) {
      flushPara()
      flushList()
      blocks.push({
        type: h1 ? 'h1' : h2 ? 'h2' : 'h3',
        text: (h1 || h2 || h3)![1].trim(),
      })
      i++
      continue
    }

    const ulMatch = trimmed.match(/^[-*]\s+(.*)/)
    const olMatch = trimmed.match(/^\d+\.\s+(.*)/)
    if (ulMatch) {
      flushPara()
      if (!list || list.type !== 'ul') {
        flushList()
        list = { type: 'ul', items: [] }
      }
      list.items.push(ulMatch[1].trim())
      i++
      continue
    }
    if (olMatch) {
      flushPara()
      if (!list || list.type !== 'ol') {
        flushList()
        list = { type: 'ol', items: [] }
      }
      list.items.push(olMatch[1].trim())
      i++
      continue
    }

    // 普通段落
    flushList()
    para.push(trimmed)
    i++
  }
  flushPara()
  flushList()
  return blocks
}

// 渲染行内加粗 **text**
function renderInline(text: string, keyBase: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((p, idx) => {
    if (/^\*\*[^*]+\*\*$/.test(p)) {
      return (
        <Text key={`${keyBase}-b-${idx}`} style={{ fontWeight: 600 }}>
          {p.slice(2, -2)}
        </Text>
      )
    }
    return <Text key={`${keyBase}-t-${idx}`}>{p}</Text>
  })
}

export default function Markdown({ source, className }: MarkdownProps) {
  const blocks = parse(source || '')
  return (
    <View className={className}>
      {blocks.map((b, idx) => {
        const key = `b-${idx}`
        switch (b.type) {
          case 'h1':
            return (
              <Text key={key} style={{ display: 'block', fontSize: '36rpx', fontWeight: 600, margin: '24rpx 0 16rpx', color: '#1d2129' }}>
                {b.text}
              </Text>
            )
          case 'h2':
            return (
              <Text key={key} style={{ display: 'block', fontSize: '32rpx', fontWeight: 600, margin: '24rpx 0 12rpx', color: '#1d2129' }}>
                {b.text}
              </Text>
            )
          case 'h3':
            return (
              <Text key={key} style={{ display: 'block', fontSize: '30rpx', fontWeight: 600, margin: '20rpx 0 10rpx', color: '#1d2129' }}>
                {b.text}
              </Text>
            )
          case 'hr':
            return <View key={key} style={{ height: '1rpx', background: '#e5e6eb', margin: '24rpx 0' }} />
          case 'ul':
            return (
              <View key={key}>
                {b.items!.map((it, i) => (
                  <View key={`${key}-li-${i}`} style={{ display: 'flex', flexDirection: 'row', margin: '8rpx 0', lineHeight: 1.6 }}>
                    <Text style={{ color: '#165dff', marginRight: '12rpx' }}>•</Text>
                    <Text style={{ flex: 1, color: '#1d2129', fontSize: '28rpx' }}>{renderInline(it, `${key}-${i}`)}</Text>
                  </View>
                ))}
              </View>
            )
          case 'ol':
            return (
              <View key={key}>
                {b.items!.map((it, i) => (
                  <View key={`${key}-li-${i}`} style={{ display: 'flex', flexDirection: 'row', margin: '8rpx 0', lineHeight: 1.6 }}>
                    <Text style={{ color: '#165dff', marginRight: '12rpx', minWidth: '32rpx' }}>{i + 1}.</Text>
                    <Text style={{ flex: 1, color: '#1d2129', fontSize: '28rpx' }}>{renderInline(it, `${key}-${i}`)}</Text>
                  </View>
                ))}
              </View>
            )
          default:
            return (
              <Text key={key} style={{ display: 'block', fontSize: '28rpx', lineHeight: 1.7, color: '#1d2129', margin: '8rpx 0' }}>
                {renderInline(b.text || '', key)}
              </Text>
            )
        }
      })}
    </View>
  )
}
