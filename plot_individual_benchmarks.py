#!/usr/bin/env python3

import csv
import json
import re
from pathlib import Path

import matplotlib.pyplot as plt


ROOT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = ROOT_DIR / 'results'
PLOTS_DIR = ROOT_DIR / 'plots' / 'individual'

BENCHMARK_RE = re.compile(r'^(?P<family>[^/]+)/(?P<args>.*)$')

ARG_RE = re.compile(r'(?P<name>[^/:]+):(?P<value>[^/]+)')


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


def load_results(path):
	with path.open() as file:
		data = json.load(file)
	return data['benchmarks']


def prepare_data(benchmarks):
	result = []

	for benchmark in benchmarks:
		if benchmark.get('run_type') != 'iteration':
			continue

		family, args = parse_benchmark_name(benchmark['name'])

		row = {
			'family': family,
			'args': args,
			'time': benchmark['real_time'],
			'time_unit': benchmark.get('time_unit', 'ns'),
		}

		for key in ('1.ME', '2.MAE', '3.RMSE', '4.Variance'):
			if key in benchmark:
				row[key] = benchmark[key]

		result.append(row)

	return result


def get_arg(row, name, default=None):
	value = row['args'].get(name, default)

	if value is None:
		return None

	try:
		return int(value)
	except ValueError:
		return value


def plot_barycentric(data, output_dir, filename):
	rows = [
		row for row in data
		if row['family'] == 'BM_barycentric'
	]

	if not rows:
		return

	rows.sort(key=lambda row: get_arg(row, 'n'))

	fig, ax = plt.subplots()

	x_values = [get_arg(row, 'n') for row in rows]
	y_values = [row['time'] for row in rows]

	with (output_dir / f'{filename}.tsv').open('w', newline='') as file:
		writer = csv.writer(file, delimiter='\t', lineterminator='\n')
		writer.writerow(['n', 'time'])
		writer.writerows(zip(x_values, y_values))

	ax.plot(
		x_values,
		y_values,
		marker='o',
	)

	for x, y in zip(x_values, y_values):
		ax.annotate(
			f'{y:.2e}',
			(x, y),
			textcoords='offset points',
			xytext=(5, 5),
		)

	ax.set_title(f'Barycentric interpolation - {filename}')
	ax.set_xlabel('n')
	ax.set_ylabel('Time (ns)')
	ax.set_xscale('log', base=2)
	ax.set_yscale('log')
	ax.minorticks_on()
	ax.grid(True, which='major')
	ax.grid(True, which='minor', alpha=0.3)

	fig.tight_layout()
	fig.savefig(output_dir / f'{filename}.svg')
	plt.close(fig)


def plot_hermite_construction(data, output_dir, filename):
	rows = [
		row for row in data
		if row['family'] == 'BM_hermite_spline'
	]

	if not rows:
		return

	types = sorted(
		{
			get_arg(row, 'type')
			for row in rows
		}
	)

	type_names = {
		0: 'Classic',
		1: 'Cardinal{0.1}',
		2: 'Akima',
		3: 'ModifiedAkima',
		4: 'Steffen',
	}

	fig, ax = plt.subplots()

	with (output_dir / f'{filename}.tsv').open('w', newline='') as file:
		writer = csv.writer(file, delimiter='\t', lineterminator='\n')
		writer.writerow(['n', 'type', 'time'])

		for spline_type in types:
			type_rows = [
				row for row in rows
				if get_arg(row, 'type') == spline_type
			]

			type_rows.sort(key=lambda row: get_arg(row, 'n'))

			type_name = type_names.get(spline_type) or f'type {spline_type}'

			x_values = [get_arg(row, 'n') for row in type_rows]
			y_values = [row['time'] for row in type_rows]

			ax.plot(
				x_values,
				y_values,
				marker='o',
				label=type_name,
			)

			writer.writerows(
				zip(
					x_values,
					[type_name] * len(x_values),
					y_values,
				)
			)

	ax.set_title(f'Hermite spline construction - {filename}')
	ax.set_xlabel('n')
	ax.set_ylabel('Time (ns)')
	ax.set_xscale('log', base=2)
	ax.set_yscale('log')
	ax.minorticks_on()
	ax.grid(True, which='major')
	ax.grid(True, which='minor', alpha=0.3)
	ax.legend()

	fig.tight_layout()
	fig.savefig(output_dir / f'{filename}.svg')
	plt.close(fig)


def plot_hermite_values(data, output_dir, filename):
	rows = [
		row for row in data
		if row['family'] == 'BM_hermite_spline_values'
	]

	if not rows:
		return

	rows.sort(key=lambda row: get_arg(row, 'n'))

	fig, ax = plt.subplots()

	x_values = [get_arg(row, 'n') for row in rows]
	y_values = [row['time'] for row in rows]

	ax.plot(
		x_values,
		y_values,
		marker='o',
	)

	with (output_dir / f'{filename}-hermite_values.tsv').open('w', newline='') as file:
		writer = csv.writer(file, delimiter='\t', lineterminator='\n')
		writer.writerow(['n', 'time'])
		writer.writerows(zip(x_values, y_values))

	for x, y in zip(x_values, y_values):
		ax.annotate(
			f'{y:.2e}',
			(x, y),
			textcoords='offset points',
			xytext=(5, 5),
		)

	ax.set_title(f'Hermite spline evaluation - {filename}')
	ax.set_xlabel('n')
	ax.set_ylabel('Time (ns)')
	ax.set_xscale('log', base=2)
	ax.set_yscale('log')
	ax.minorticks_on()
	ax.grid(True, which='major')
	ax.grid(True, which='minor', alpha=0.3)

	fig.tight_layout()
	fig.savefig(output_dir / f'{filename}-hermite_values.svg')
	plt.close(fig)


def main():
	PLOTS_DIR.mkdir(parents=True, exist_ok=True)

	for path in sorted(RESULTS_DIR.glob('*.json')):
		print(f'Processing {path.name}')

		benchmarks = load_results(path)
		data = prepare_data(benchmarks)

		plot_barycentric(data, PLOTS_DIR, path.stem)
		plot_hermite_construction(data, PLOTS_DIR, path.stem)
		plot_hermite_values(data, PLOTS_DIR, path.stem)


if __name__ == '__main__':
	main()