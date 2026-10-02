/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_MBEDTLS_NUTTX_CONFIG_H
#define BRICKWRIGHT_MBEDTLS_NUTTX_CONFIG_H

/* Minimal PSA surface used by the Zephyr Bluetooth host: AES-128 ECB/CMAC,
 * P-256 ECDH and random bytes.  Do not pull the general TLS/X.509 profile
 * into the hub image. */
#define MBEDTLS_PSA_CRYPTO_C
#define MBEDTLS_PSA_CRYPTO_CONFIG
#define MBEDTLS_PSA_CRYPTO_CONFIG_FILE "brickwright/psa_crypto_nuttx_config.h"
#define MBEDTLS_PSA_CRYPTO_EXTERNAL_RNG
#define MBEDTLS_AES_C
#define MBEDTLS_CIPHER_C
#define MBEDTLS_CMAC_C
#define MBEDTLS_BIGNUM_C
#define MBEDTLS_ECP_C
#define MBEDTLS_ECDH_C
#define MBEDTLS_ECP_DP_SECP256R1_ENABLED
#define MBEDTLS_AES_ROM_TABLES
#define MBEDTLS_MPI_MAX_SIZE 32
#define MBEDTLS_ECP_WINDOW_SIZE 2
#define MBEDTLS_ECP_FIXED_POINT_OPTIM 0

#endif
