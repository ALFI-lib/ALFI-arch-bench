cmake_minimum_required(VERSION 3.22)

project(ALFI_ARCH_BENCH LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(ALFI_ARCH "x86_64" CACHE STRING "Target architecture")
set_property(CACHE ALFI_ARCH PROPERTY STRINGS x86_64 rv64)

set(ALFI_COMPILER "gcc" CACHE STRING "Compiler")
set_property(CACHE ALFI_COMPILER PROPERTY STRINGS gcc clang)

set(ALFI_PROFILE "O0" CACHE STRING "Optimization profile")
set_property(CACHE ALFI_PROFILE PROPERTY STRINGS O0 O3 O3-openmp)

if(ALFI_ARCH STREQUAL "x86_64")
	set(ALFI_ARCH_FLAGS -march=x86-64)
elseif(ALFI_ARCH STREQUAL "rv64")
	set(ALFI_ARCH_FLAGS -march=rv64gv -mabi=lp64d)
else()
	message(FATAL_ERROR "Unsupported ALFI_ARCH: ${ALFI_ARCH}")
endif()

if(ALFI_COMPILER STREQUAL "gcc")
	# do nothing
elseif(ALFI_COMPILER STREQUAL "clang")
	if(ALFI_ARCH STREQUAL "rv64")
		set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} --target=riscv64-linux-gnu")
		add_compile_options(--target=riscv64-linux-gnu)
		add_link_options(--target=riscv64-linux-gnu)
	endif()
else()
	message(FATAL_ERROR "Unsupported ALFI_COMPILER: ${ALFI_COMPILER}")
endif()

if(ALFI_PROFILE STREQUAL "O0")
	set(ALFI_PROFILE_FLAGS -O0)
	set(ALFI_OPENMP OFF)
elseif(ALFI_PROFILE STREQUAL "O3")
	set(ALFI_PROFILE_FLAGS -O3)
	set(ALFI_OPENMP OFF)
elseif(ALFI_PROFILE STREQUAL "O3-openmp")
	set(ALFI_PROFILE_FLAGS -O3)
	set(ALFI_OPENMP ON)
else()
	message(FATAL_ERROR "Unsupported ALFI_PROFILE: ${ALFI_PROFILE}")
endif()

set(ALFI_ENABLE_EXAMPLES OFF)
set(ALFI_ENABLE_TESTS OFF)
set(ALFI_ENABLE_BENCHES ON)

add_subdirectory(ALFI)

foreach(bench_target IN ITEMS bench_barycentric bench_hermite)
	target_compile_options(${bench_target} PRIVATE ${ALFI_ARCH_FLAGS} ${ALFI_PROFILE_FLAGS})

	if(ALFI_OPENMP)
		if(ALFI_COMPILER STREQUAL "gcc")
			target_compile_options(${bench_target} PRIVATE -fopenmp)
			target_link_options(${bench_target} PRIVATE -fopenmp)
		elseif(ALFI_COMPILER STREQUAL "clang")
			target_compile_options(${bench_target} PRIVATE -fopenmp=libgomp)
			target_link_options(${bench_target} PRIVATE -fopenmp=libgomp)
		endif()
	endif()
endforeach()