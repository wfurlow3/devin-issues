== Plan ==
Summary: Add comprehensive random seed management to ensure reproducible training results across Python, NumPy, and PyTorch (including CUDA).
Steps:
  1. Create a `set_seed(seed)` utility function in `src/utils.py` that sets: `random.seed()`, `np.random.seed()`, `torch.manual_seed()`, `torch.cuda.manual_seed_all()`, and configures `torch.backends.cudnn.deterministic=True` and `torch.backends.cudnn.benchmark=False`
  2. Update `src/train_mlm.py:run_experiment()` to call `set_seed()` instead of the current inline seed setting (lines 173-175)
  3. Update `src/dataset.py:make_dataloaders()` to accept a `generator` argument and pass a seeded `torch.Generator` to DataLoader for reproducible shuffling
  4. Update `src/los/baselines/train_los_gru.py:main()` to use `set_seed()` and add `random.seed()` (currently missing Python random)
  5. Update `src/los/baselines/train_los_transformer.py:main()` to use `set_seed()` and add `random.seed()` (currently missing Python random)
  6. Add docstring to `src/config.py:SEED` explaining its purpose for reproducibility
  7. Validate by running training twice with same seed and comparing final validation metrics
Risks:
  1. Setting `cudnn.deterministic=True` may slow down training by 10-20% on GPU
  2. Some PyTorch operations have no deterministic implementation - may need `torch.use_deterministic_algorithms(True)` with fallback handling
  3. DataLoader with `num_workers>0` requires `worker_init_fn` for full reproducibility - current code uses default workers
Confidence: 0.90