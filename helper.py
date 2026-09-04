#!/usr/bin/env python3

import argparse
import os
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
BUILD_DIR = ROOT_DIR / 'build'
RESULTS_DIR = ROOT_DIR / 'results'

ARCHITECTURES = {
	'x86_64': {
		'cmake_arch': 'x86_64',
		'qemu': ['qemu-x86_64'],
	},
	'riscv64': {
		'cmake_arch': 'rv64',
		'qemu': ['qemu-riscv64', '-L', '/usr/riscv64-linux-gnu'],
	},
}

COMPILERS = {
	'gcc': {
		'x86_64': 'x86_64-linux-gnu-g++',
		'riscv64': 'riscv64-linux-gnu-g++',
	},
	'clang': {
		'x86_64': 'clang++',
		'riscv64': 'clang++',
	},
}

PROFILES = {
	'O0': {
		'cmake_profile': 'O0',
	},
	'O3': {
		'cmake_profile': 'O3',
	},
	'O3-openmp': {
		'cmake_profile': 'O3-openmp',
	},
}


def config_name(arch, compiler, profile):
	return f'{arch}-{compiler}-{profile}'


def build_dir(arch, compiler, profile):
	return BUILD_DIR / config_name(arch, compiler, profile)


def benchmark_path(arch, compiler, profile):
	return build_dir(arch, compiler, profile) / 'ALFI' / 'benches' / 'bench_barycentric'


def result_path(arch, compiler, profile):
	return RESULTS_DIR / f'{config_name(arch, compiler, profile)}.txt'


def run_command(command, output_file=None):
	print('+', ' '.join(map(str, command)))

	if output_file is None:
		subprocess.run(command, check=True)
		return

	RESULTS_DIR.mkdir(parents=True, exist_ok=True)

	with output_file.open('w') as file:
		subprocess.run(
			command,
			check=True,
			stdout=file,
			stderr=subprocess.STDOUT,
		)


def configure(arch, compiler, profile):
	directory = build_dir(arch, compiler, profile)

	directory.mkdir(parents=True, exist_ok=True)

	run_command([
		'cmake',
		'-S', str(ROOT_DIR),
		'-B', str(directory),
		f'-DCMAKE_CXX_COMPILER={COMPILERS[compiler][arch]}',
		f'-DALFI_ARCH={ARCHITECTURES[arch]['cmake_arch']}',
		f'-DALFI_COMPILER={compiler}',
		f'-DALFI_PROFILE={profile}',
	])


def build(arch, compiler, profile):
	directory = build_dir(arch, compiler, profile)

	configure(arch, compiler, profile)

	run_command([
		'cmake',
		'--build', str(directory),
		'--target', 'bench_barycentric',
		'--parallel',
	])


def run(arch, compiler, profile):
	executable = benchmark_path(arch, compiler, profile)

	if not executable.exists():
		build(arch, compiler, profile)

	command = [*ARCHITECTURES[arch]['qemu'], str(executable), '--benchmark_format=console']

	output_file = result_path(arch, compiler, profile)

	run_command(command, output_file)

	print(f'Result saved to {output_file}')


def all_configs():
	for arch in ARCHITECTURES:
		for compiler in COMPILERS:
			for profile in PROFILES:
				yield arch, compiler, profile


def require_config_args(parser, args):
	if not args.arch or not args.compiler or not args.profile:
		parser.error('this action requires --arch, --compiler and --profile')


def main():
	parser = argparse.ArgumentParser()

	parser.add_argument(
		'action',
		choices=['configure', 'build', 'run'],
	)

	parser.add_argument(
		'--arch',
		choices=list(ARCHITECTURES),
	)

	parser.add_argument(
		'--compiler',
		choices=list(COMPILERS),
	)

	parser.add_argument(
		'--profile',
		choices=list(PROFILES),
	)

	args = parser.parse_args()

	architectures = [args.arch] if args.arch else list(ARCHITECTURES)
	compilers = [args.compiler] if args.compiler else list(COMPILERS)
	profiles = [args.profile] if args.profile else list(PROFILES)
	configs = [(arch, compiler, profile) for arch in architectures for compiler in compilers for profile in profiles]

	for arch, compiler, profile in configs:
		configure(arch, compiler, profile)

		if args.action in {'build', 'run'}:
			build(arch, compiler, profile)

		if args.action == 'run':
			run(arch, compiler, profile)


if __name__ == '__main__':
	main()