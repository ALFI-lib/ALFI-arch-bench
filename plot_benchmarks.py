#!/usr/bin/env python3

import csv
import json
import re
from pathlib import Path

import matplotlib.pyplot as plt


ROOT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = ROOT_DIR / 'results'
PLOTS_DIR = ROOT_DIR / 'plots'

BENCHMARK_FILE_RE = re.compile(
	r'^bench_(?P<benchmark>.+)-(?P<arch>x86_64|riscv64)-'
	r'(?P<compiler>gcc|clang)-(?P<profile>O3-openmp|O0|O3)\.json$'
)

BENCHMARK_RE = re.compile(r'^(?P<family>[^/]+)/(?P<args>.*)$')
ARG_RE = re.compile(r'(?P<name>[^/:]+):(?P<value>[^/]*)')

TYPE_NAMES = {
	0: 'Classic',
	1: 'Cardinal{0.1}',
	2: 'Akima',
	3: 'ModifiedAkima',
	4: 'Steffen',
}


def parse_result_filename(filename):
	match = BENCHMARK_FILE_RE.match(filename)
	if not match:
		return None

	return {
		'benchmark': match.group('benchmark'),
		'arch': match.group('arch'),
		'compiler': match.group('compiler'),
		'profile': match.group('profile'),
	}


def parse_benchmark_name(name):
	match = BENCHMARK_RE.match(name)
	if not match:
		return name, {}

	family = match.group('family')
	args = {
		match.group('name'): match.group('value')
		for match in ARG_RE.finditer(match.group('args'))
	}

	return family, args


def get_arg(row, name, default=None):
	value = row['args'].get(name, default)

	if value is None:
		return None

	try:
		return int(value)
	except ValueError:
		return value


def load_results(path, metadata):
	with path.open() as file:
		data = json.load(file)

	result = []

	for benchmark in data['benchmarks']:
		if benchmark.get('run_type') != 'iteration':
			continue

		family, args = parse_benchmark_name(benchmark['name'])

		result.append({
			'benchmark': metadata['benchmark'],
			'arch': metadata['arch'],
			'compiler': metadata['compiler'],
			'profile': metadata['profile'],
			'family': family,
			'args': args,
			'time': benchmark['real_time'],
			'time_unit': benchmark.get('time_unit', 'ns'),
		})

	return result


def load_all_results():
	data = []

	for path in sorted(RESULTS_DIR.glob('*.json')):
		metadata = parse_result_filename(path.name)

		if metadata is None:
			print(f'Skipping {path.name}')
			continue

		print(f'Processing {path.name}')
		data.extend(load_results(path, metadata))

	return data


def plot_series(ax, rows, label):
	rows.sort(key=lambda row: get_arg(row, 'n'))

	x_values = [get_arg(row, 'n') for row in rows]
	y_values = [row['time'] for row in rows]

	ax.plot(
		x_values,
		y_values,
		marker='o',
		label=label,
	)

	for x, y in zip(x_values, y_values):
		ax.annotate(
			f'{y:.2e}',
			(x, y),
			textcoords='offset points',
			xytext=(5, 5),
		)

	return x_values, y_values


def save_series_tsv(output_path, series_data):
	with output_path.open('w', newline='') as file:
		writer = csv.writer(file, delimiter='\t', lineterminator='\n')
		writer.writerow(['n', 'series', 'time'])

		for label, x_values, y_values in series_data:
			writer.writerows(
				zip(
					x_values,
					[label] * len(x_values),
					y_values,
				)
			)


def configure_axis(ax):
	ax.set_xlabel('n')
	ax.set_ylabel('Time (ns)')
	ax.set_xscale('log', base=2)
	ax.set_yscale('log')
	ax.minorticks_on()
	ax.grid(True, which='major')
	ax.grid(True, which='minor', alpha=0.3)


def plot_barycentric_comparison(
	data,
	series,
	title,
	output_path,
):
	rows_by_series = []

	for label, conditions in series:
		rows = [
			row for row in data
			if row['family'] == 'BM_barycentric'
			and all(row[key] == value for key, value in conditions.items())
		]

		if rows:
			rows_by_series.append((label, rows))

	if not rows_by_series:
		return

	fig, ax = plt.subplots()
	series_data = []

	for label, rows in rows_by_series:
		x_values, y_values = plot_series(ax, rows, label)
		series_data.append((label, x_values, y_values))

	ax.set_title(title)
	configure_axis(ax)
	ax.legend()

	fig.tight_layout()
	fig.savefig(output_path)
	plt.close(fig)

	save_series_tsv(output_path.with_suffix('.tsv'), series_data)


def plot_hermite_construction_comparison(
	data,
	series,
	title_prefix,
	output_dir,
):
	output_dir.mkdir(parents=True, exist_ok=True)

	for spline_type in sorted(TYPE_NAMES):
		rows_by_series = []

		for label, conditions in series:
			rows = [
				row for row in data
				if row['family'] == 'BM_hermite_spline'
				and get_arg(row, 'type') == spline_type
				and all(row[key] == value for key, value in conditions.items())
			]

			if rows:
				rows_by_series.append((label, rows))

		if not rows_by_series:
			continue

		fig, ax = plt.subplots()
		series_data = []

		for label, rows in rows_by_series:
			x_values, y_values = plot_series(ax, rows, label)
			series_data.append((label, x_values, y_values))

		type_name = TYPE_NAMES.get(spline_type, f'type {spline_type}')

		ax.set_title(f'{title_prefix} - Hermite spline construction - {type_name}')
		configure_axis(ax)
		ax.legend()

		output_path = output_dir / f'hermite_construction_type{spline_type}.svg'

		fig.tight_layout()
		fig.savefig(output_path)
		plt.close(fig)

		save_series_tsv(output_path.with_suffix('.tsv'), series_data)


def plot_hermite_values_comparison(
	data,
	series,
	title,
	output_path,
):
	rows_by_series = []

	for label, conditions in series:
		rows = [
			row for row in data
			if row['family'] == 'BM_hermite_spline_values'
			and all(row[key] == value for key, value in conditions.items())
		]

		if rows:
			rows_by_series.append((label, rows))

	if not rows_by_series:
		return

	fig, ax = plt.subplots()
	series_data = []

	for label, rows in rows_by_series:
		x_values, y_values = plot_series(ax, rows, label)
		series_data.append((label, x_values, y_values))

	ax.set_title(title)
	configure_axis(ax)
	ax.legend()

	fig.tight_layout()
	fig.savefig(output_path)
	plt.close(fig)

	save_series_tsv(output_path.with_suffix('.tsv'), series_data)


def plot_architecture_comparisons(data):
	output_dir = PLOTS_DIR / 'architecture'
	output_dir.mkdir(parents=True, exist_ok=True)

	architectures = {
		'x86_64': 'x86_64',
		'riscv64': 'riscv64',
	}

	available_compilers = sorted(
		{row['compiler'] for row in data}
	)
	available_profiles = sorted(
		{row['profile'] for row in data}
	)

	for compiler in available_compilers:
		for profile in available_profiles:
			series = [
				(
					architectures['x86_64'],
					{
						'compiler': compiler,
						'profile': profile,
						'arch': 'x86_64',
					},
				),
				(
					architectures['riscv64'],
					{
						'compiler': compiler,
						'profile': profile,
						'arch': 'riscv64',
					},
				),
			]

			prefix = f'{compiler}-{profile}'

			plot_barycentric_comparison(
				data,
				series,
				f'Barycentric interpolation - {prefix}',
				output_dir / f'barycentric-{prefix}.svg',
			)

			plot_hermite_construction_comparison(
				data,
				series,
				f'{prefix}',
				output_dir / f'hermite-construction-{prefix}',
			)

			plot_hermite_values_comparison(
				data,
				series,
				f'Hermite spline evaluation - {prefix}',
				output_dir / f'hermite-values-{prefix}.svg',
			)


def plot_compiler_comparisons(data):
	output_dir = PLOTS_DIR / 'compiler'
	output_dir.mkdir(parents=True, exist_ok=True)

	architectures = sorted(
		{row['arch'] for row in data}
	)
	available_profiles = sorted(
		{row['profile'] for row in data}
	)

	for arch in architectures:
		for profile in available_profiles:
			series = [
				(
					'GCC',
					{
						'arch': arch,
						'profile': profile,
						'compiler': 'gcc',
					},
				),
				(
					'Clang',
					{
						'arch': arch,
						'profile': profile,
						'compiler': 'clang',
					},
				),
			]

			prefix = f'{arch}-{profile}'

			plot_barycentric_comparison(
				data,
				series,
				f'Barycentric interpolation - {prefix}',
				output_dir / f'barycentric-{prefix}.svg',
			)

			plot_hermite_construction_comparison(
				data,
				series,
				f'{prefix}',
				output_dir / f'hermite-construction-{prefix}',
			)

			plot_hermite_values_comparison(
				data,
				series,
				f'Hermite spline evaluation - {prefix}',
				output_dir / f'hermite-values-{prefix}.svg',
			)


def plot_profile_comparisons(data):
	output_dir = PLOTS_DIR / 'profile'
	output_dir.mkdir(parents=True, exist_ok=True)

	architectures = sorted(
		{row['arch'] for row in data}
	)
	available_compilers = sorted(
		{row['compiler'] for row in data}
	)

	profiles = ['O0', 'O3', 'O3-openmp']

	for arch in architectures:
		for compiler in available_compilers:
			series = [
				(
					profile,
					{
						'arch': arch,
						'compiler': compiler,
						'profile': profile,
					},
				)
				for profile in profiles
			]

			prefix = f'{arch}-{compiler}'

			plot_barycentric_comparison(
				data,
				series,
				f'Barycentric interpolation - {prefix}',
				output_dir / f'barycentric-{prefix}.svg',
			)

			plot_hermite_construction_comparison(
				data,
				series,
				f'{prefix}',
				output_dir / f'hermite-construction-{prefix}',
			)

			plot_hermite_values_comparison(
				data,
				series,
				f'Hermite spline evaluation - {prefix}',
				output_dir / f'hermite-values-{prefix}.svg',
			)


def main():
	PLOTS_DIR.mkdir(parents=True, exist_ok=True)

	data = load_all_results()

	plot_architecture_comparisons(data)
	plot_compiler_comparisons(data)
	plot_profile_comparisons(data)


if __name__ == '__main__':
	main()