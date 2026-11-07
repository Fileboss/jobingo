import type { Page } from '@playwright/test';
import type { components } from '#lib/api/schema.d.ts';

type Schemas = components['schemas'];
type UsageReport = Schemas['UsageReport'];
type CallSummary = Schemas['CallSummary'];
type CallDetail = Schemas['CallDetail'];
type AppEvent = Schemas['AppEvent'];
type EvalTask = Schemas['EvalTask'];

const figures = {
	calls: 0,
	ok: 0,
	failed: 0,
	errors: 0,
	retried: 0,
	input_tokens: 0,
	output_tokens: 0,
	cache_read_tokens: 0,
	cache_write_tokens: 0,
	cost_usd: '0',
	latency_p50_ms: null,
	latency_p95_ms: null
};

function days(count: number) {
	const today = new Date();
	return Array.from({ length: count }, (_, i) => {
		const day = new Date(today.getFullYear(), today.getMonth(), today.getDate() - (count - 1 - i));
		const iso = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`;
		return { day: iso, calls: 0, cost_usd: '0' };
	});
}

const call = (id: number, task: string, status: CallSummary['status']): CallSummary => ({
	id,
	created_at: '2026-11-06T09:30:00+01:00',
	task,
	prompt_version: 1,
	model: 'claude-haiku-5-5',
	status,
	error: status === 'ok' ? null : 'validation failed',
	attempts: 1,
	input_tokens: 1200,
	output_tokens: 90,
	cache_read_tokens: 0,
	cache_write_tokens: 0,
	cost_usd: '0.000165',
	latency_ms: 640
});

const event = (id: number, name: string, level: AppEvent['level'], llm_call_id: number | null) => ({
	id,
	created_at: '2026-11-06T09:30:01+01:00',
	level,
	name,
	fields: { task: 'score_offer' },
	llm_call_id
});

/** The observability API in memory, for Playwright: journalled calls on fictional data. */
export class FakeObservabilityApi {
	measured = true;
	calls: CallSummary[] = [
		call(3, 'score_offer', 'ok'),
		call(2, 'classify_message', 'failed'),
		call(1, 'score_offer', 'ok')
	];
	events: AppEvent[] = [
		event(12, 'sync.failed', 'WARNING', null),
		event(11, 'offer.scored', 'INFO', 3),
		event(10, 'llm.call', 'INFO', 3)
	];
	evals: EvalTask[] = [{ task: 'select_cv_content', shipped_version: 5, current: null, runs: [] }];
	usageDays: number[] = [];
	callQueries: URLSearchParams[] = [];
	eventQueries: URLSearchParams[] = [];

	usage(count: number): UsageReport {
		const daily = days(count);
		const total = this.measured
			? {
					...figures,
					calls: 3,
					ok: 2,
					failed: 1,
					input_tokens: 3600,
					output_tokens: 270,
					cost_usd: '0.000495',
					latency_p50_ms: 640,
					latency_p95_ms: 640
				}
			: figures;
		if (this.measured)
			daily[daily.length - 1] = { ...daily.at(-1)!, calls: 3, cost_usd: '0.000495' };
		return {
			days: count,
			since: `${daily[0].day}T00:00:00+01:00`,
			configured: true,
			models: [
				{ tier: 'fast', model: 'claude-haiku-5-5', thinking: 'off', effort: 'medium' },
				{ tier: 'writing', model: 'claude-sonnet-5-5', thinking: 'off', effort: 'medium' }
			],
			total,
			tasks: this.measured
				? [
						{ ...total, task: 'score_offer', calls: 2, failed: 0, cost_usd: '0.00033' },
						{ ...figures, task: 'classify_message', calls: 1, failed: 1, cost_usd: '0.000165' }
					]
				: [],
			daily,
			budget: {
				today_usd: total.cost_usd,
				daily_cap_usd: '2',
				month_usd: total.cost_usd,
				monthly_cap_usd: '30'
			}
		};
	}

	detail(id: number): CallDetail | undefined {
		const summary = this.calls.find((c) => c.id === id);
		if (!summary) return undefined;
		return {
			...summary,
			system_prompt: 'Note l’offre de 0 à 5.',
			user_prompt: '<offre>Développeuse Python, Nantes</offre>',
			parameters: { model: summary.model, max_tokens: 500 },
			answer: { score: 4 },
			response: null,
			purged_at: null,
			events: this.events.filter((e) => e.llm_call_id === id)
		};
	}

	async install(page: Page) {
		await page.route('**/api/observability/usage*', async (route) => {
			const count = Number(new URL(route.request().url()).searchParams.get('days') ?? 30);
			this.usageDays.push(count);
			await route.fulfill({ json: this.usage(count) });
		});
		await page.route(/\/api\/observability\/calls(\?.*)?$/, async (route) => {
			const query = new URL(route.request().url()).searchParams;
			this.callQueries.push(query);
			const calls = this.calls.filter(
				(c) =>
					(!query.get('task') || c.task === query.get('task')) &&
					(!query.get('status') || c.status === query.get('status'))
			);
			await route.fulfill({
				json: { calls, next_before_id: null, tasks: ['classify_message', 'score_offer'] }
			});
		});
		await page.route(/\/api\/observability\/calls\/\d+$/, async (route) => {
			const id = Number(route.request().url().split('/').at(-1));
			const detail = this.detail(id);
			if (!detail) return route.fulfill({ status: 404, json: { detail: 'Appel introuvable' } });
			await route.fulfill({ json: detail });
		});
		await page.route('**/api/observability/evals', async (route) => {
			await route.fulfill({ json: this.evals });
		});
		await page.route('**/api/observability/events*', async (route) => {
			const query = new URL(route.request().url()).searchParams;
			this.eventQueries.push(query);
			const text = query.get('q') ?? '';
			const events = this.events.filter((e) => !text || e.name.includes(text));
			await route.fulfill({ json: { events, next_before_id: null } });
		});
	}
}

/** A recorded eval run, fictional, as `evals/run.py` writes it. */
export function evalRun(score: number, failing: Record<string, unknown>[] = []) {
	return {
		suite: 'select_cv_content',
		metric: 'cas où toute la sélection attendue est retenue',
		prompt_version: 5,
		setup: 'claude-sonnet-5-5.off-medium',
		model: 'claude-sonnet-5-5',
		thinking: 'off',
		effort: 'medium',
		score,
		threshold: null,
		passed: null,
		cases: 8,
		detail: { cases: `${Math.round(score * 8)}/8`, refused_rewrites: 1 },
		spend: {
			live_calls: 8,
			cached_calls: 0,
			input_tokens: 52000,
			output_tokens: 2900,
			cache_read_tokens: 0,
			cache_write_tokens: 6000,
			cost_usd: '0.0412',
			latency_p50_ms: 4300,
			latency_p95_ms: 6400
		},
		run_at: '2026-11-07T09:00:00Z',
		regraded_from_cache: false,
		failing
	};
}
