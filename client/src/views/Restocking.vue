<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div v-if="lastOrder" class="success-banner" role="status">
        <div class="success-title">{{ t('restocking.success.title') }}</div>
        <div class="success-details">
          <strong>{{ t('restocking.success.orderNumber', { number: lastOrder.order_number }) }}</strong>
          <span>{{ t('restocking.success.total', { total: money(lastOrder.total_cost) }) }}</span>
          <span>{{ t('restocking.success.expectedDelivery', { date: formatDate(lastOrder.expected_delivery) }) }}</span>
          <router-link to="/orders" class="banner-link">{{ t('restocking.success.viewOrders') }}</router-link>
          <button type="button" class="apply-btn" @click="resetSelection">{{ t('restocking.applyRecommendation') }}</button>
        </div>
      </div>
      <div v-if="submitError" class="error" role="alert">{{ submitError }}</div>

      <div class="card budget-card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budgetControl') }}</h3>
        </div>
        <div class="budget-controls">
          <input
            v-model.number="budget"
            type="range"
            min="0"
            :max="maxBudget"
            step="100"
            class="budget-slider"
            :aria-label="t('restocking.budgetSlider')"
          />
          <input
            v-model.number="budget"
            type="number"
            min="0"
            :max="maxBudget"
            step="100"
            class="budget-number"
            :aria-label="t('restocking.budgetInput')"
          />
          <span class="budget-display">{{ money(budget) }}</span>
          <span v-if="currentCurrency !== 'USD'" class="currency-note">{{ t('restocking.budgetInUsd') }}</span>
        </div>
        <p class="hint">{{ t('restocking.budgetHint') }}</p>
      </div>

      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.summary.budget') }}</div>
          <div class="stat-value">{{ money(budget) }}</div>
        </div>
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.summary.selectedTotal') }}</div>
          <div class="stat-value">{{ money(selectedTotal) }}</div>
        </div>
        <div :class="['stat-card', remaining < 0 ? 'danger' : 'success']">
          <div class="stat-label">{{ t('restocking.summary.remaining') }}</div>
          <div class="stat-value">{{ money(remaining) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.summary.longestLeadTime') }}</div>
          <div class="stat-value">{{ t('restocking.daysValue', { count: longestLeadTime }) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.summary.itemCount') }}</div>
          <div class="stat-value">{{ selectedLines.length }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendationTitle') }}</h3>
          <button
            type="button"
            class="place-order-btn"
            :disabled="!canSubmit"
            @click="submitOrder"
          >
            {{ submitting ? t('restocking.submitting') : t('restocking.placeOrder') }}
          </button>
        </div>
        <div v-if="overBudget" class="over-budget">{{ t('restocking.overBudget') }}</div>
        <div v-if="needItems.length === 0" class="empty">{{ t('restocking.noNeed') }}</div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th class="col-check">{{ t('restocking.table.select') }}</th>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th class="num">{{ t('restocking.table.need') }}</th>
                <th class="num">{{ t('restocking.table.quantity') }}</th>
                <th class="num">{{ t('restocking.table.unitCost') }}</th>
                <th class="num">{{ t('restocking.table.lineTotal') }}</th>
                <th class="num">{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in needItems" :key="item.item_sku">
                <td class="col-check">
                  <input
                    type="checkbox"
                    :checked="selection[item.item_sku] && selection[item.item_sku].selected"
                    :aria-label="item.item_sku"
                    @change="toggleItem(item, $event.target.checked)"
                  />
                </td>
                <td><strong>{{ item.item_sku }}</strong></td>
                <td>{{ item.item_name }}</td>
                <td>
                  <span :class="['badge', item.trend]">{{ t(`trends.${item.trend}`) }}</span>
                </td>
                <td class="num">{{ item.need }}</td>
                <td class="num">
                  <input
                    type="number"
                    min="0"
                    :max="item.need"
                    step="1"
                    class="qty-input"
                    :value="selection[item.item_sku] ? selection[item.item_sku].quantity : 0"
                    :aria-label="`${item.item_sku} ${t('restocking.table.quantity')}`"
                    @input="setQuantity(item, $event.target.value)"
                  />
                </td>
                <td class="num">{{ money(item.unit_cost, 2) }}</td>
                <td class="num"><strong>{{ money(lineTotal(item), 2) }}</strong></td>
                <td class="num">{{ item.lead_time_days }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrencyWithDecimals } from '../utils/currency'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, currentLocale } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const allForecasts = ref([])
    const budget = ref(0)
    // sku -> { selected: bool, quantity: int }
    const selection = ref({})
    const submitting = ref(false)
    const submitError = ref(null)
    const lastOrder = ref(null)

    const money = (amount, decimals = 0) =>
      formatCurrencyWithDecimals(amount, currentCurrency.value, decimals)

    const formatDate = (dateString) => {
      const d = new Date(dateString)
      if (isNaN(d.getTime())) return dateString
      const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
      return d.toLocaleDateString(locale, { year: 'numeric', month: 'short', day: 'numeric' })
    }

    // Items with positive need, sorted: increasing trend first, then need * unit_cost descending
    const needItems = computed(() => {
      return allForecasts.value
        .map(f => ({ ...f, need: Math.max(f.forecasted_demand - f.current_demand, 0) }))
        .filter(f => f.need > 0)
        .sort((a, b) => {
          const ra = a.trend === 'increasing' ? 0 : 1
          const rb = b.trend === 'increasing' ? 0 : 1
          if (ra !== rb) return ra - rb
          return b.need * b.unit_cost - a.need * a.unit_cost
        })
    })

    const maxBudget = computed(() => {
      const total = needItems.value.reduce((sum, i) => sum + i.need * i.unit_cost, 0)
      return Math.ceil(total / 100 - 1e-9) * 100
    })

    // Greedy fill of the budget; partial quantity when an item does not fit fully
    const recommendation = computed(() => {
      const result = {}
      let remainingBudget = Math.max(Number(budget.value) || 0, 0)
      for (const item of needItems.value) {
        let qty = 0
        const fullCost = item.need * item.unit_cost
        if (fullCost <= remainingBudget + 1e-9) {
          qty = item.need
        } else if (item.unit_cost > 0) {
          const partial = Math.floor((remainingBudget + 1e-9) / item.unit_cost)
          if (partial >= 1) qty = Math.min(partial, item.need)
        }
        if (qty > 0) remainingBudget -= qty * item.unit_cost
        result[item.item_sku] = { selected: qty > 0, quantity: qty }
      }
      return result
    })

    const resetSelection = () => {
      const copy = {}
      for (const [sku, entry] of Object.entries(recommendation.value)) {
        copy[sku] = { ...entry }
      }
      selection.value = copy
    }

    const clearSelection = () => {
      const cleared = {}
      for (const item of needItems.value) {
        cleared[item.item_sku] = { selected: false, quantity: 0 }
      }
      selection.value = cleared
    }

    // Selection is re-initialized from the recommendation whenever it changes
    // (budget moves or data loads), so manual edits are reset on slider move.
    watch(recommendation, resetSelection, { immediate: true })

    const selectedLines = computed(() => {
      return needItems.value
        .filter(i => {
          const s = selection.value[i.item_sku]
          return s && s.selected && s.quantity > 0
        })
        .map(i => ({ ...i, quantity: selection.value[i.item_sku].quantity }))
    })

    const lineTotal = (item) => {
      const s = selection.value[item.item_sku]
      return s && s.selected ? s.quantity * item.unit_cost : 0
    }

    const selectedTotal = computed(() =>
      selectedLines.value.reduce((sum, l) => sum + l.quantity * l.unit_cost, 0)
    )
    const remaining = computed(() => (Number(budget.value) || 0) - selectedTotal.value)
    const overBudget = computed(() => selectedTotal.value > (Number(budget.value) || 0) + 1e-9)
    const longestLeadTime = computed(() =>
      selectedLines.value.reduce((max, l) => Math.max(max, l.lead_time_days), 0)
    )

    const canSubmit = computed(() =>
      selectedLines.value.length > 0 && !overBudget.value && !submitting.value
    )

    const toggleItem = (item, checked) => {
      const entry = selection.value[item.item_sku] || { selected: false, quantity: 0 }
      entry.selected = checked
      if (checked && entry.quantity <= 0) entry.quantity = item.need
      selection.value[item.item_sku] = entry
    }

    const setQuantity = (item, raw) => {
      let qty = parseInt(raw, 10)
      if (isNaN(qty) || qty < 0) qty = 0
      if (qty > item.need) qty = item.need
      selection.value[item.item_sku] = { selected: qty > 0, quantity: qty }
    }

    const submitOrder = async () => {
      if (!canSubmit.value) return
      submitting.value = true
      submitError.value = null
      try {
        const order = await api.createRestockOrder({
          items: selectedLines.value.map(l => ({ item_sku: l.item_sku, quantity: l.quantity })),
          budget: Number(budget.value) || 0
        })
        lastOrder.value = order
        clearSelection()
      } catch (err) {
        const detail = err.response && err.response.data && err.response.data.detail
        if (typeof detail === 'string') {
          submitError.value = detail
        } else if (Array.isArray(detail)) {
          submitError.value = detail.map(d => d.msg).join('; ')
        } else {
          submitError.value = t('restocking.submitError')
        }
        lastOrder.value = null
      } finally {
        submitting.value = false
      }
    }

    const loadForecasts = async () => {
      try {
        loading.value = true
        error.value = null
        allForecasts.value = await api.getDemandForecasts()
        // Default budget: about half of the cost of covering every need
        budget.value = Math.round(maxBudget.value / 2 / 100) * 100
      } catch (err) {
        error.value = t('restocking.loadError', { message: err.message })
      } finally {
        loading.value = false
      }
    }

    onMounted(loadForecasts)

    return {
      t,
      loading,
      error,
      budget,
      maxBudget,
      selection,
      needItems,
      selectedLines,
      selectedTotal,
      remaining,
      overBudget,
      longestLeadTime,
      canSubmit,
      submitting,
      submitError,
      lastOrder,
      money,
      formatDate,
      lineTotal,
      toggleItem,
      setQuantity,
      submitOrder,
      resetSelection,
      currentCurrency
    }
  }
}
</script>

<style scoped>
.budget-controls {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.budget-slider {
  flex: 1;
  accent-color: #3b82f6;
}

.budget-number {
  width: 120px;
  padding: 0.5rem 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  color: #0f172a;
  font-size: 0.938rem;
}

.budget-display {
  min-width: 100px;
  font-weight: 700;
  color: #0f172a;
  text-align: right;
}

.hint {
  margin: 0.75rem 0 0;
  color: #64748b;
  font-size: 0.813rem;
}

.success-banner {
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  color: #065f46;
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 1rem;
}

.success-title {
  font-weight: 700;
  margin-bottom: 0.375rem;
}

.success-details {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem 1.5rem;
  align-items: center;
  font-size: 0.938rem;
}

.banner-link {
  color: #2563eb;
  font-weight: 600;
  text-decoration: underline;
}

.currency-note {
  color: #64748b;
  font-size: 0.813rem;
}

.apply-btn {
  background: white;
  color: #0f172a;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 0.25rem 0.75rem;
  font-size: 0.813rem;
  font-weight: 600;
  cursor: pointer;
}

.place-order-btn {
  background: #0f172a;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 0.5rem 1.25rem;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
}

.place-order-btn:hover:not(:disabled) {
  background: #1e293b;
}

.place-order-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.over-budget {
  color: #991b1b;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
  margin-bottom: 0.75rem;
  font-size: 0.875rem;
}

.empty {
  text-align: center;
  padding: 2rem;
  color: #64748b;
}

.col-check {
  width: 60px;
  text-align: center;
}

.num {
  text-align: right;
}

.qty-input {
  width: 80px;
  padding: 0.375rem 0.5rem;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  text-align: right;
  color: #0f172a;
}
</style>
