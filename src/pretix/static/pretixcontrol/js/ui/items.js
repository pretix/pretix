$("#btn_reorder_categories").click(function() {
	$("#products_table").attr('hidden', '');
	$("#categories_table").removeAttr('hidden');
	return false;
});
$("#btn_reorder_categories_done").click(function() {
	//$("#products_table").removeAttr('hidden');
	//$("#categories_table").attr('hidden', '');
	location=location;
	return false;
});
