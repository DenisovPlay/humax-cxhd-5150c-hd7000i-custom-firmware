    .set    noreorder
    .set    noat
    .text
    .globl  _start
_start:
/* ─── точки входа: лоадер может прыгнуть на 0x000, 0x008 или 0x508 ─── */
    bal     stub                    /* 0x000 */
    nop
    bal     stub                    /* 0x008 */
    nop

    .org    0x200
/* ═══ PIC-стаб: переносит весь образ на 0x800B0000 с любого адреса ═══ */
stub:
    bal     2f
    nop
2:  move    $t0, $ra                  /* $t0 = runtime (2f) */
    /* li заменён на addiu ниже: 2f - stub = 8 */
    addiu   $t0, $t0, -0x208           /* $t0 = RUNTIME IMAGE BASE (2f на 0x208) */

    li      $t1, 0xA0000000
    or      $t1, $t1, $t0              /* $t1 = src uncached */
    li      $t2, 0xA00AFAE0          /* $t2 = dst uncached (0x800B0000-0x520) */
    li      $t5, 0x12345678          /* SIZE: патчим после сборки = 0x600+kern */
    li      $t3, 0x800AFAE0          /* dst cached (для сравнения) */
    sltu    $t4, $t0, $t3              /* src < dst ? */
    bnez    $t4, backward
    nop

forward:                            /* src >= dst: копируем снизу вверх */
    addu    $t6, $t1, $t5
1:  lw      $t7, 0($t1)
    sw      $t7, 0($t2)
    addiu   $t1, 4
    addiu   $t2, 4
    bne     $t1, $t6, 1b
    nop
    b       done
    nop

backward:                           /* src < dst: копируем сверху вниз */
    addu    $t1, $t1, $t5
    addu    $t2, $t2, $t5
    li      $t8, 0xA0000000
    or      $t8, $t8, $t0              /* $t8 = src base uncached */
2:  addiu   $t1, -4
    addiu   $t2, -4
    lw      $t7, 0($t1)
    sw      $t7, 0($t2)
    bne     $t1, $t8, 2b
    nop

done:
    li      $t8, 0x21436587          /* ENTRY: патчим после сборки */
    jr      $t8
    nop

    .org    0x508
    bal     stub                    /* 0x508: конвенция CCX app-header */
    nop

    .org    0x520
    .globl  kernel_off
kernel_off = .
