#!/usr/bin/env python3

import argparse
import subprocess
import tempfile
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
BUILD_DIR = ROOT_DIR / 'build'
RESULTS_DIR = ROOT_DIR / 'results'
RESULTS_SYSTEM_DIR = ROOT_DIR / 'results-system'

SYSTEM_IMAGES = {
	'x86_64': ROOT_DIR / 'debian-13-genericcloud-amd64.qcow2',
	'riscv64': ROOT_DIR / 'debian-13-generic-riscv64.qcow2',
}

SYSTEM_IMAGE_URLS = {
	'x86_64': 'https://cloud.debian.org/images/cloud/trixie/latest/debian-13-genericcloud-amd64.qcow2',
	'riscv64': 'https://cloud.debian.org/images/cloud/trixie/latest/debian-13-generic-riscv64.qcow2',
}

ARCHITECTURES = {
	'x86_64': {
		'cmake_arch': 'x86_64',
		'qemu': ['qemu-x86_64'],
		'system_qemu': 'qemu-system-x86_64',
	},
	'riscv64': {
		'cmake_arch': 'rv64',
		'qemu': ['qemu-riscv64', '-L', '/usr/riscv64-linux-gnu'],
		'system_qemu': 'qemu-system-riscv64',
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


def benchmark_path(arch, compiler, profile, benchmark):
	directory = build_dir(arch, compiler, profile)
	matches = list(directory.rglob(benchmark))
	if not matches:
		raise FileNotFoundError(f'Benchmark executable not found: {benchmark} in {directory}')
	if len(matches) > 1:
		raise RuntimeError(f'Multiple benchmark executables found for {benchmark} in {directory}: ' + ', '.join(map(str, matches)))
	return matches[0]


def result_path(arch, compiler, profile, benchmark):
	return RESULTS_DIR / f'{benchmark}-{config_name(arch, compiler, profile)}.txt'


def system_result_path(arch, compiler, profile, benchmark):
	return RESULTS_SYSTEM_DIR / f'{benchmark}-{config_name(arch, compiler, profile)}.txt'


def run_command(command, output_file=None):
	print('+', ' '.join(map(str, command)))

	if output_file is None:
		subprocess.run(command, check=True)
		return

	output_file.parent.mkdir(parents=True, exist_ok=True)

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
		'-DCMAKE_BUILD_TYPE=Release',
		f'-DCMAKE_CXX_COMPILER={COMPILERS[compiler][arch]}',
		f'-DALFI_ARCH={ARCHITECTURES[arch]['cmake_arch']}',
		f'-DALFI_COMPILER={compiler}',
		f'-DALFI_PROFILE={profile}',
	])


def build(arch, compiler, profile, benchmark):
	directory = build_dir(arch, compiler, profile)

	configure(arch, compiler, profile)

	run_command([
		'cmake',
		'--build', str(directory),
		'--target', benchmark,
		'--parallel',
	])


def run(arch, compiler, profile, benchmark):
	try:
		executable = benchmark_path(arch, compiler, profile, benchmark)
	except FileNotFoundError:
		build(arch, compiler, profile, benchmark)
		executable = benchmark_path(arch, compiler, profile, benchmark)

	command = [
		*ARCHITECTURES[arch]['qemu'],
		str(executable),
		'--benchmark_format=json',
	]

	output_file = result_path(arch, compiler, profile, benchmark)

	run_command(command, output_file)

	print(f'Result saved to {output_file}')


def download_system_image(arch):
	image = SYSTEM_IMAGES[arch]
	if image.exists():
		return image

	run_command([
		'wget',
		'-O', str(image),
		SYSTEM_IMAGE_URLS[arch],
	])

	return image


def create_cloud_init(directory):
	user_data = directory / 'user-data'
	meta_data = directory / 'meta-data'
	iso = directory / 'cidata.iso'

	user_data.write_text(
'''#cloud-config
users:
  - name: dev
    groups: [sudo]
    shell: /bin/bash
    lock_passwd: false
    plain_text_passwd: dev
    sudo: ALL=(ALL) NOPASSWD:ALL

ssh_pwauth: true

package_update: true
packages:
  - openssh-server
  - libgomp1

runcmd:
  - systemctl enable ssh
  - systemctl restart ssh
'''
	)

	meta_data.write_text(
'''instance-id: alfi-arch-bench
local-hostname: alfi-arch-bench
'''
	)

	run_command([
		'genisoimage',
		'-output', str(iso),
		'-volid', 'cidata',
		'-joliet',
		'-rock',
		str(user_data),
		str(meta_data),
	])

	return iso


def wait_for_ssh(port):
	for _ in range(180):
		result = subprocess.run(
			[
				'ssh',
				'-o', 'StrictHostKeyChecking=no',
				'-o', 'UserKnownHostsFile=/dev/null',
				'-o', 'ConnectTimeout=2',
				'-p', str(port),
				'dev@127.0.0.1',
				'true',
			],
			# stdout=subprocess.DEVNULL,
			# stderr=subprocess.DEVNULL,
		)

		if result.returncode == 0:
			return

		time.sleep(2)

	raise RuntimeError('SSH connection to virtual machine failed')


def ssh_command(port, command, output_file=None):
	try:
		run_command([
			'ssh',
			'-o', 'StrictHostKeyChecking=no',
			'-o', 'UserKnownHostsFile=/dev/null',
			'-p', str(port),
			'dev@127.0.0.1',
			command,
		], output_file)
	except subprocess.CalledProcessError as error:
		print(f'SSH command failed with exit code {error.returncode}: {command}')
		raise


def scp_to_vm(port, source, destination):
	run_command([
		'scp',
		'-O',
		'-o', 'StrictHostKeyChecking=no',
		'-o', 'UserKnownHostsFile=/dev/null',
		'-P', str(port),
		str(source),
		f'dev@127.0.0.1:{destination}',
	])


def run_system(arch, compiler, profile, benchmark):
	try:
		executable = benchmark_path(arch, compiler, profile, benchmark)
	except FileNotFoundError:
		build(arch, compiler, profile, benchmark)
		executable = benchmark_path(arch, compiler, profile, benchmark)

	image = download_system_image(arch)

	with tempfile.TemporaryDirectory(dir=ROOT_DIR) as temp_dir:
		directory = Path(temp_dir)
		overlay = directory / 'vm.qcow2'
		cidata = create_cloud_init(directory)

		run_command([
			'qemu-img',
			'create',
			'-f', 'qcow2',
			'-b', str(image),
			'-F', 'qcow2',
			str(overlay),
			'10G',
		])

		port = 22000 + (subprocess.os.getpid() % 1000)

		if arch == 'x86_64':
			command = [
				'qemu-system-x86_64',
				'-enable-kvm',
				'-m', '4096',
				'-smp', '16',
				'-drive', f'file={overlay},format=qcow2,if=virtio',
				'-drive', f'file={cidata},format=raw,media=cdrom',
				'-netdev', f'user,id=net,hostfwd=tcp::{port}-:22',
				'-device', 'virtio-net-pci,netdev=net',
				'-nographic',
			]
		else:
			command = [
				'qemu-system-riscv64',
				'-machine', 'virt',
				'-cpu', 'rv64',
				'-m', '4096',
				'-smp', '16',
				'-kernel', '/usr/lib/u-boot/qemu-riscv64_smode/uboot.elf',
				'-device', 'virtio-blk-device,drive=hd',
				'-drive', f'file={overlay},format=qcow2,if=none,id=hd',
				'-drive', f'file={cidata},format=raw,media=cdrom',
				'-netdev', f'user,id=net,hostfwd=tcp::{port}-:22',
				'-device', 'virtio-net-device,netdev=net',
				'-object', 'rng-random,filename=/dev/urandom,id=rng',
				'-device', 'virtio-rng-device,rng=rng',
				'-nographic',
			]

		vm = subprocess.Popen(
			command,
			# stdout=subprocess.DEVNULL,
			# stderr=subprocess.DEVNULL,
		)

		try:
			wait_for_ssh(port)
			ssh_command(port, 'cloud-init status --wait')

			vm_executable = f'/tmp/{benchmark}'

			scp_to_vm(port, executable, vm_executable)

			ssh_command(port, f'chmod +x {vm_executable}')

			output_file = system_result_path(arch, compiler, profile, benchmark)

			ssh_command(port, f'{vm_executable} --benchmark_format=json', output_file)

			print(f'Result saved to {output_file}')

		finally:
			vm.terminate()

			try:
				vm.wait(timeout=10)
			except subprocess.TimeoutExpired:
				vm.kill()
				vm.wait()


def main():
	parser = argparse.ArgumentParser()

	parser.add_argument(
		'action',
		choices=['configure', 'build', 'run', 'run-system'],
	)

	parser.add_argument(
		'--benchmark',
		required=True,
		help='benchmark executable name',
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
	configs = [
		(arch, compiler, profile)
		for arch in architectures
		for compiler in compilers
		for profile in profiles
	]

	for arch, compiler, profile in configs:
		configure(arch, compiler, profile)

		if args.action in {'build', 'run', 'run-system'}:
			build(arch, compiler, profile, args.benchmark)

		if args.action == 'run':
			run(arch, compiler, profile, args.benchmark)

		if args.action == 'run-system':
			run_system(arch, compiler, profile, args.benchmark)


if __name__ == '__main__':
	main()