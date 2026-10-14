class FoodProduct {
  final String barcode;
  final String name;
  final String brand;
  final String ingredients;
  final String allergens;
  final String? nutritionGrade;
  final Map<String, dynamic> nutrients;
  final String? imageUrl;

  const FoodProduct({
    required this.barcode,
    required this.name,
    required this.brand,
    required this.ingredients,
    required this.allergens,
    required this.nutrients,
    this.nutritionGrade,
    this.imageUrl,
  });

  factory FoodProduct.fromJson(Map<String, dynamic> json) {
    final product = json['product'] is Map
        ? Map<String, dynamic>.from(json['product'] as Map)
        : <String, dynamic>{};

    final rawNutrients = product['nutriments'];

    return FoodProduct(
      barcode: json['code']?.toString() ?? '',
      name: product['product_name']?.toString() ?? 'Unknown product',
      brand: product['brands']?.toString() ?? 'Unknown brand',
      ingredients: product['ingredients_text']?.toString() ?? '',
      allergens: product['allergens']?.toString() ?? '',
      nutritionGrade: product['nutrition_grades']?.toString(),
      nutrients: rawNutrients is Map
          ? Map<String, dynamic>.from(rawNutrients)
          : <String, dynamic>{},
      imageUrl: product['image_front_url']?.toString(),
    );
  }
}
