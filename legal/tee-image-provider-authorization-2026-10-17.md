# Tee Image Provider Authorization Assessment

**Assessment date:** 2026-10-17<br>
**Status:** Internal research for the exact hosted route below. This is not legal advice or attorney clearance.

## Scope

This assessment concerns only the Hugging Face Inference Providers route from the model `black-forest-labs/FLUX.1-Krea-dev` through provider `fal-ai` to Fal's hosted endpoint `fal-ai/flux/krea`. The current tee-generation allowlist records that exact provider, model, and endpoint tuple.

Fal's public endpoint listing presents this hosted endpoint as permitting commercial use. That is an endpoint/service-level statement for use through Fal's hosted API and remains subject to Fal's applicable terms and the account's terms. It is not a license to download, self-host, redistribute, or commercially operate the Krea weights.

## Source Findings

- Hugging Face's [model provider mapping](https://huggingface.co/api/models/black-forest-labs/FLUX.1-Krea-dev?expand%5B%5D=inferenceProviderMapping) maps `black-forest-labs/FLUX.1-Krea-dev` with provider `fal-ai` to provider model ID `fal-ai/flux/krea`. This is the exact routed model mapping used by the implementation.
- Fal's hosted FLUX.1 Krea endpoint lists **"Commercial use permitted"** in the **License** row under [Technical Specifications](https://fal.ai/models/fal-ai/flux/krea#technical-specifications). Fal's [Terms of Service](https://fal.ai/legal/terms-of-service) apply to use of Fal services; endpoint availability or a public listing does not verify account-specific contract terms.
- Hugging Face documents [Inference Provider selection and routing](https://huggingface.co/docs/inference-providers/en/index), including selection of a named provider, and [pricing and billing](https://huggingface.co/docs/inference-providers/en/pricing). For Hugging Face-routed requests, Hugging Face proxies the request and bills through the Hugging Face account at provider rates. Pass-through billing is a payment path, not a copyright or commercial-use license.
- The [Krea model card](https://huggingface.co/black-forest-labs/FLUX.1-Krea-dev) identifies the downloadable model as subject to the [FLUX.1 [dev] Non-Commercial License](https://huggingface.co/black-forest-labs/FLUX.1-dev/blob/main/LICENSE.md). Its output-use language does not convert commercial operation of the downloadable weights into an authorized use under that license.
- Black Forest Labs' [FLUX.1 Krea [dev] announcement](https://bfl.ai/announcements/flux-1-krea-dev) distinguishes the open-weight release from partner API endpoints, identifies Fal as an API endpoint partner, and points to separate commercial licensing for the weights. Krea's [open-weights release](https://www.krea.ai/blog/flux-krea-open-source-release) provides additional model-release context.

## Boundaries and Open Questions

The hosted Fal endpoint statement is not generalized here to self-hosted Krea weights, FLUX.1 [dev], any other FLUX model, another provider's route, or another account's terms. Only the exact hosted endpoint mapping above is allowlisted. Pollinations remains excluded because its exact model and license have not been verified. OpenAI remains default-disabled and is not allowlisted; enabling its toggle alone does not authorize a route.

Account-specific agreements, custom provider keys, organizational terms, and any separate commercial licenses are unverified. Recheck the primary sources and applicable account terms before changing the route, model, provider, or allowlist. No attorney has reviewed or cleared this assessment.