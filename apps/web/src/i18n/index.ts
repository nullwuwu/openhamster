import { createI18n } from 'vue-i18n'

export const LOCALE_STORAGE_KEY = 'quant-trader.locale'

export type SupportedLocale = 'zh-CN' | 'en-US'

const DEFAULT_LOCALE: SupportedLocale = 'zh-CN'

const messages = {
  'zh-CN': {
    common: {
      noData: '暂无数据',
      polling: '实时轮询',
      enabled: '启用',
      disabled: '禁用',
      status: '状态',
      symbol: '标的',
      strategy: '策略',
      created: '创建时间',
      id: 'ID',
      time: '时间',
      side: '方向',
      qty: '数量',
      price: '价格',
      runStatus: {
        queued: '排队中',
        running: '运行中',
        succeeded: '成功',
        failed: '失败',
      },
    },
    shell: {
      appTitle: '量化交易台',
      consoleTitle: '研究控制台',
      runBacktest: '发起回测',
      language: '语言',
      nav: {
        overview: '总览',
        strategies: '策略',
        backtests: '回测',
        experiments: '实验',
        trading: '交易',
      },
    },
    overview: {
      backtests: '回测任务',
      experiments: '实验任务',
      runningJobs: '运行任务',
      latestEquity: '最新权益',
      paperEquityCurve: '模拟盘权益曲线',
      totalEquity: '总权益',
      latestBacktest: '最近回测',
      latestExperiment: '最近实验',
      noRunYet: '暂无运行记录',
      strategy: '策略',
      symbol: '标的',
      status: '状态',
    },
    strategies: {
      title: '策略注册表',
      subtitle: '用于 Dashboard/API 的内置策略快照',
    },
    backtests: {
      createTitle: '创建回测任务',
      queueAction: '加入回测队列',
      submitting: '提交中...',
      runsTitle: '回测运行列表',
      form: {
        symbol: '标的代码',
        strategy: '策略名称',
        provider: '数据源',
        start: '开始日期',
        end: '结束日期',
        capital: '初始资金',
      },
    },
    experiments: {
      createTitle: '创建实验任务',
      optimizerAction: '加入参数优化队列',
      walkforwardAction: '加入 Walkforward 队列',
      runsTitle: '实验运行列表',
      kind: '类型',
      form: {
        symbol: '标的代码',
        strategy: '策略名称',
        provider: '数据源',
        start: '开始日期',
        end: '结束日期',
        topN: 'Top N',
      },
    },
    trading: {
      equity: '模拟盘权益',
      positions: '当前持仓',
      latestOrders: '最近订单',
    },
  },
  'en-US': {
    common: {
      noData: 'No data',
      polling: 'live polling',
      enabled: 'enabled',
      disabled: 'disabled',
      status: 'Status',
      symbol: 'Symbol',
      strategy: 'Strategy',
      created: 'Created',
      id: 'ID',
      time: 'Time',
      side: 'Side',
      qty: 'Qty',
      price: 'Price',
      runStatus: {
        queued: 'Queued',
        running: 'Running',
        succeeded: 'Succeeded',
        failed: 'Failed',
      },
    },
    shell: {
      appTitle: 'Quant Trader',
      consoleTitle: 'Research Console',
      runBacktest: 'Run Backtest',
      language: 'Language',
      nav: {
        overview: 'Overview',
        strategies: 'Strategies',
        backtests: 'Backtests',
        experiments: 'Experiments',
        trading: 'Trading',
      },
    },
    overview: {
      backtests: 'Backtests',
      experiments: 'Experiments',
      runningJobs: 'Running Jobs',
      latestEquity: 'Latest Equity',
      paperEquityCurve: 'Paper Equity Curve',
      totalEquity: 'Total Equity',
      latestBacktest: 'Latest Backtest',
      latestExperiment: 'Latest Experiment',
      noRunYet: 'No run yet',
      strategy: 'Strategy',
      symbol: 'Symbol',
      status: 'Status',
    },
    strategies: {
      title: 'Strategy Registry',
      subtitle: 'Built-in strategy snapshots used by dashboard/API.',
    },
    backtests: {
      createTitle: 'Create Backtest Run',
      queueAction: 'Queue Backtest',
      submitting: 'submitting...',
      runsTitle: 'Backtest Runs',
      form: {
        symbol: 'symbol',
        strategy: 'strategy',
        provider: 'provider',
        start: 'start',
        end: 'end',
        capital: 'capital',
      },
    },
    experiments: {
      createTitle: 'Run Experiment',
      optimizerAction: 'Queue Optimizer',
      walkforwardAction: 'Queue Walkforward',
      runsTitle: 'Experiment Runs',
      kind: 'Kind',
      form: {
        symbol: 'symbol',
        strategy: 'strategy',
        provider: 'provider',
        start: 'start',
        end: 'end',
        topN: 'top_n',
      },
    },
    trading: {
      equity: 'Paper Equity',
      positions: 'Current Positions',
      latestOrders: 'Latest Orders',
    },
  },
}

function normalizeLocale(locale: string | null | undefined): SupportedLocale | null {
  if (!locale) return null

  const normalized = locale.toLowerCase()
  if (normalized.startsWith('zh')) return 'zh-CN'
  if (normalized.startsWith('en')) return 'en-US'

  return null
}

function resolveInitialLocale(): SupportedLocale {
  try {
    const stored = normalizeLocale(localStorage.getItem(LOCALE_STORAGE_KEY))
    if (stored) return stored
  } catch {
    // Ignore localStorage errors and continue with browser detection.
  }

  const browserLocale = normalizeLocale(navigator.language)
  return browserLocale ?? DEFAULT_LOCALE
}

export const i18n = createI18n({
  legacy: false,
  locale: resolveInitialLocale(),
  fallbackLocale: DEFAULT_LOCALE,
  messages,
})

export function setAppLocale(locale: SupportedLocale): void {
  i18n.global.locale.value = locale
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale)
  } catch {
    // Ignore localStorage errors.
  }
}

export function getCurrentLocale(): SupportedLocale {
  return i18n.global.locale.value as SupportedLocale
}
