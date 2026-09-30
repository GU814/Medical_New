import React, { useMemo, useState } from 'react';
import { View, Text } from '@tarojs/components';
import classnames from 'classnames';
import styles from './index.module.scss';
import type { ReactStep, ReactStepRef } from '@/types';

/** 步骤类型 -> 中文标签 + 图标(与后端 STEP_* 常量一一对应) */
const STEP_META: Record<ReactStep['type'], { icon: string; label: string }> = {
  thought: { icon: '💭', label: '思考' },
  action: { icon: '⚡', label: '动作' },
  observation: { icon: '🔍', label: '观察' },
  final: { icon: '✅', label: '作答' },
  fallback: { icon: '⚠️', label: '降级' },
  note: { icon: 'ℹ️', label: '说明' },
};

const STEP_ORDER: ReactStep['type'][] = [
  'note',
  'thought',
  'action',
  'observation',
  'final',
  'fallback',
];

/** 只渲染后端真实支持的步骤类型(脏数据/未来新增类型一律不显示,避免 UI 出现未知块) */
const isKnownType = (t?: string): t is ReactStep['type'] =>
  !!t && (STEP_ORDER as string[]).includes(t);

function ms(step?: ReactStep): string {
  const v = step?.elapsed_ms;
  if (!v || v <= 0) return '';
  return v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${v}ms`;
}

/** 引用来源一行摘要,例如「fever.md#1 · 相关度 0.87」 */
function refLabel(r: ReactStepRef): string {
  const loc = r.chunk_index === null || r.chunk_index === undefined ? '' : `#${r.chunk_index}`;
  const src = r.source ? `${r.source}${loc}` : r.doc_id || '未知来源';
  const score = r.score ? ` · 相关度 ${Number(r.score).toFixed(2)}` : '';
  return `${src}${score}`;
}

function RefList({ refs }: { refs?: ReactStepRef[] }) {
  if (!refs || refs.length === 0) return null;
  return (
    <View className={styles.refList}>
      {refs.map((r, i) => (
        <View className={styles.refItem} key={`${r.doc_id || 'ref'}-${r.n}-${i}`}>
          <Text className={styles.refBadge}>[{r.n}]</Text>
          <View className={styles.refBody}>
            <Text className={styles.refSource}>{refLabel(r)}</Text>
            {r.quote ? (
              <Text className={styles.refQuote}>"{r.quote}"</Text>
            ) : null}
          </View>
        </View>
      ))}
    </View>
  );
}

/** 句子级溯源:逐句展示来源,没引用的句子标注「通用表述」而不是丢弃 */
function SentenceTrace({ step }: { step: ReactStep }) {
  const sentences = step.sentences || [];
  if (sentences.length === 0) return null;
  return (
    <View className={styles.sentenceBlock}>
      <Text className={styles.sentenceTitle}>📌 句子级溯源({sentences.length} 句)</Text>
      {sentences.map((s, i) => (
        <View className={classnames(styles.sentence, !s.cited && styles.sentenceNoRef)} key={i}>
          <Text className={styles.sentenceIndex}>{i + 1}</Text>
          <View className={styles.sentenceBody}>
            <Text className={styles.sentenceText}>{s.text}</Text>
            {s.cited && s.refs && s.refs.length > 0 ? (
              <RefList refs={s.refs} />
            ) : s.inferred && s.refs && s.refs.length > 0 ? (
              <View className={styles.sentenceInferred}>
                <Text className={styles.sentenceHint}>
                  以下来源由系统按字面重合度推断绑定,非模型显式引用,仅供参考:
                </Text>
                <RefList refs={s.refs} />
              </View>
            ) : (
              <Text className={styles.sentenceHint}>通用表述,无直接知识来源</Text>
            )}
          </View>
        </View>
      ))}
    </View>
  );
}

function StepRow({ step }: { step: ReactStep }) {
  const meta = STEP_META[step.type] || STEP_META.note;
  const cost = ms(step);
  const argsText = step.args
    ? Object.entries(step.args)
        .map(([k, v]) => `${k}=${String(v)}`)
        .join(' ')
    : '';
  return (
    <View
      className={classnames(
        styles.step,
        step.status === 'error' && styles.stepError,
        step.status === 'timeout' && styles.stepTimeout
      )}
    >
      <View className={styles.stepHead}>
        <Text className={styles.stepIcon}>{meta.icon}</Text>
        <Text className={styles.stepLabel}>{meta.label}</Text>
        {step.tool ? <Text className={styles.stepTool}>{step.tool}</Text> : null}
        {cost ? <Text className={styles.stepCost}>{cost}</Text> : null}
      </View>
      {step.text ? <Text className={styles.stepText}>{step.text}</Text> : null}
      {argsText ? <Text className={styles.stepArgs}>{argsText}</Text> : null}
      <RefList refs={step.refs} />
      {step.type === 'final' ? <SentenceTrace step={step} /> : null}
      {step.error ? <Text className={styles.stepErrorText}>错误码:{step.error}</Text> : null}
    </View>
  );
}

/**
 * 推理过程时间线(可折叠)。
 *
 * 设计约束:
 * - 只要 steps 非空就完整展示,不提供「暂无推理过程」这类空态;
 * - 步骤缺失时由外层(consult 页)传入 stepsMissingReason 展示具体原因。
 */
export default function ReasoningSteps({ steps, defaultOpen = false }: { steps: ReactStep[]; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const ordered = useMemo(
    () => [...steps].sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0)),
    [steps]
  );
  const totalCost = useMemo(
    () => ordered.reduce((s, x) => s + (x.elapsed_ms || 0), 0),
    [ordered]
  );
  if (ordered.length === 0) return null;

  return (
    <View className={styles.block}>
      <View className={styles.header} onClick={() => setOpen((v) => !v)}>
        <Text className={styles.icon}>🧠</Text>
        <Text className={styles.title}>推理过程</Text>
        <Text className={styles.meta}>
          {ordered.length} 步 · 约 {(totalCost / 1000).toFixed(1)}s
        </Text>
        <Text className={styles.toggle}>{open ? '收起 ▲' : '展开 ▼'}</Text>
      </View>
      {open ? (
        <View className={styles.body}>
          {ordered.map((s) => (
            <StepRow key={`${s.seq}-${s.type}`} step={s} />
          ))}
        </View>
      ) : (
        <View className={styles.preview}>
          {ordered.slice(0, 3).map((s) => (
            <Text key={`p-${s.seq}`} className={styles.previewItem}>
              {STEP_META[s.type]?.icon || '•'} {s.text || s.type}
            </Text>
          ))}
          {ordered.length > 3 ? (
            <Text className={styles.previewItem}>…还有 {ordered.length - 3} 步</Text>
          ) : null}
        </View>
      )}
    </View>
  );
}

/** 统一入口:过滤脏数据后再渲染,避免 undefined 步骤把整块 UI 打崩 */
export function ReasoningStepsSafe(props: { steps?: ReactStep[]; defaultOpen?: boolean }) {
  const clean = (props.steps || []).filter((s) => s && isKnownType(s.type));
  if (clean.length === 0) return null;
  return <ReasoningSteps steps={clean} defaultOpen={props.defaultOpen} />;
}
